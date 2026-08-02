from django.db import IntegrityError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Participant, Team
from .serializers import (
    ClaimResetSerializer,
    ParticipantClaimSerializer,
    TeamCreateSerializer,
    TeamAnnouncementSerializer,
    TeamDeleteSerializer,
    TeamEndSerializer,
    TeamPlannedEndSerializer,
    TeamRevealModeSerializer,
    TeamRulesSerializer,
)
from .services import (
    AdminAccessError,
    ClaimError,
    MatchingError,
    claim_participant,
    create_team_announcement,
    create_result_notifications,
    create_team_with_matching,
    delete_team,
    end_team_and_retain_chat,
    get_team_dashboard,
    get_team_countdown,
    get_my_teams,
    reset_participant_claim,
    release_manual_results,
    update_team_planned_end,
    update_team_reveal_mode,
    update_team_rules,
)
from .leaderboard_services import award_service_access_scores, leaderboard_payload
from apps.quizzes.services import QuizConflictConfirmationRequired


class TeamCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TeamCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        try:
            team = create_team_with_matching(
                owner=request.user,
                validated_data=serializer.validated_data,
            )
        except MatchingError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IntegrityError:
            return Response(
                {"code": ["이미 사용 중인 팀 코드입니다."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "code": team.code,
                "status": team.status,
                "reveal_mode": team.reveal_mode,
                "reveal_status": team.reveal_status,
                "participant_count": team.participants.count(),
                "planned_end_date": team.planned_end_date,
                "planned_end_timezone": team.planned_end_timezone,
            },
            status=status.HTTP_201_CREATED,
        )


class TeamDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, code):
        try:
            team = Team.objects.get(code=code)
        except Team.DoesNotExist:
            return Response(
                {"detail": "존재하지 않는 팀 코드입니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "code": team.code,
                "status": team.status,
                "is_joinable": team.status == Team.Status.ACTIVE,
                "rules": team.rules,
            }
        )

    def delete(self, request, code):
        team = _get_admin_team(request, code)
        if isinstance(team, Response):
            return team

        serializer = TeamDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["confirmation_code"] != team.code:
            return Response(
                {"confirmation_code": ["팀 코드가 일치하지 않습니다."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            delete_team(team=team)
        except AdminAccessError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyTeamListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"teams": get_my_teams(request.user)})


class TeamLeaderboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, code):
        team = _get_team(code)
        if isinstance(team, Response):
            return team
        if team.owner_id != request.user.id and not Participant.objects.filter(team=team, claimed_by=request.user).exists():
            return Response({"detail": "이 팀의 리더보드를 볼 권한이 없습니다."}, status=status.HTTP_403_FORBIDDEN)
        return Response(leaderboard_payload(team=team, user=request.user))


class ServiceAccessScoreView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        awarded_team_count = award_service_access_scores(user=request.user)
        return Response({"awarded_team_count": awarded_team_count})


class UnclaimedParticipantListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, code):
        team = _get_active_team(code)
        if isinstance(team, Response):
            return team

        participants = list(
            Participant.objects.filter(team=team, claimed_by__isnull=True)
            .order_by("id")
            .values("id", "display_name")
        )
        return Response({"participants": participants})


class ParticipantClaimView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, code):
        team = _get_active_team(code)
        if isinstance(team, Response):
            return team

        serializer = ParticipantClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            participant = claim_participant(
                team=team,
                user=request.user,
                participant_id=serializer.validated_data["participant_id"],
            )
        except ClaimError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "participant": {
                    "id": participant.id,
                    "display_name": participant.display_name,
                },
                "assigned_to": {
                    "display_name": participant.assigned_to.display_name,
                },
            }
        )


class MyAssignmentView(APIView):
    """현재 사용자가 이미 Claim한 참가자의 배정 결과만 반환한다."""

    permission_classes = [IsAuthenticated]

    def get(self, request, code):
        team = _get_active_team(code)
        if isinstance(team, Response):
            return team

        participant = (
            Participant.objects.filter(team=team, claimed_by=request.user)
            .select_related("assigned_to")
            .first()
        )
        if participant is None:
            return Response({"is_claimed": False})

        return Response(
            {
                "is_claimed": True,
                "participant": {
                    "id": participant.id,
                    "display_name": participant.display_name,
                },
                "assigned_to": {
                    "display_name": participant.assigned_to.display_name,
                },
                "anonymous_nickname": participant.anonymous_nickname,
            }
        )


class TeamAdminDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, code):
        team = _get_admin_team(request, code)
        if isinstance(team, Response):
            return team
        return Response(get_team_dashboard(team))


class TeamPlannedEndView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, code):
        team = _get_admin_team(request, code)
        if isinstance(team, Response):
            return team

        serializer = TeamPlannedEndSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            team = update_team_planned_end(team=team, **serializer.validated_data)
        except QuizConflictConfirmationRequired as error:
            return Response(
                {
                    "detail": str(error),
                    "code": "QUIZ_COLLISION_CONFIRMATION_REQUIRED",
                    "quiz_round_id": error.round_id,
                },
                status=status.HTTP_409_CONFLICT,
            )
        except AdminAccessError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "planned_end_date": team.planned_end_date,
                "planned_end_timezone": team.planned_end_timezone,
            }
        )


class TeamRevealModeView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, code):
        team = _get_admin_team(request, code)
        if isinstance(team, Response):
            return team

        serializer = TeamRevealModeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            team = update_team_reveal_mode(team=team, **serializer.validated_data)
        except AdminAccessError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "reveal_mode": team.reveal_mode,
                "reveal_status": team.reveal_status,
            }
        )


class TeamRulesView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, code):
        team = _get_admin_team(request, code)
        if isinstance(team, Response):
            return team

        serializer = TeamRulesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            team = update_team_rules(team=team, **serializer.validated_data)
        except AdminAccessError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"rules": team.rules})


class TeamAnnouncementView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, code):
        team = _get_admin_team(request, code)
        if isinstance(team, Response):
            return team

        serializer = TeamAnnouncementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            sent_count = create_team_announcement(team=team, **serializer.validated_data)
        except AdminAccessError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"sent_count": sent_count}, status=status.HTTP_201_CREATED)


class TeamCountdownView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, code):
        team = _get_team(code)
        if isinstance(team, Response):
            return team
        if not Participant.objects.filter(team=team, claimed_by=request.user).exists():
            return Response(
                {"detail": "본인 확인을 완료한 참여자만 종료 예정일을 조회할 수 있습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(get_team_countdown(team))


class ClaimResetView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, code):
        team = _get_admin_team(request, code)
        if isinstance(team, Response):
            return team
        if team.status != Team.Status.ACTIVE:
            return Response(
                {"detail": "진행 중인 팀의 Claim만 초기화할 수 있습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ClaimResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reset_participant_claim(team=team, participant_id=serializer.validated_data["participant_id"])
        except ClaimError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TeamEndView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, code):
        team = _get_admin_team(request, code)
        if isinstance(team, Response):
            return team

        serializer = TeamEndSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["confirmation_code"] != team.code:
            return Response(
                {"confirmation_code": ["팀 코드가 일치하지 않습니다."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            ended_team = end_team_and_retain_chat(team=team)
        except AdminAccessError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        if ended_team.reveal_status == Team.RevealStatus.AUTO_RELEASED:
            create_result_notifications(ended_team)
        return Response(
            {
                "code": ended_team.code,
                "status": ended_team.status,
                "reveal_mode": ended_team.reveal_mode,
                "reveal_status": ended_team.reveal_status,
            }
        )


class TeamResultReleaseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, code):
        team = _get_admin_team(request, code)
        if isinstance(team, Response):
            return team

        try:
            team = release_manual_results(team=team)
        except AdminAccessError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        create_result_notifications(team)
        return Response({"reveal_status": team.reveal_status})


class TeamResultView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, code):
        team = _get_team(code)
        if isinstance(team, Response):
            return team
        if team.status != Team.Status.ENDED:
            return Response(
                {"detail": "게임 종료 후에만 결과를 확인할 수 있습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if team.reveal_status == Team.RevealStatus.MANUAL_PENDING:
            return Response(
                {
                    "detail": "마니또 결과는 관리자가 별도로 공개합니다.",
                    "reveal_mode": team.reveal_mode,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            me = Participant.objects.select_related("assigned_to").get(team=team, claimed_by=request.user)
            cared_for_me = Participant.objects.get(team=team, assigned_to=me)
        except Participant.DoesNotExist:
            return Response(
                {"detail": "이 팀에서 확인한 참여자 정보를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "i_cared_for": me.assigned_to.display_name,
                "cared_for_me": cared_for_me.display_name,
            }
        )


def _get_active_team(code):
    team = _get_team(code)
    if isinstance(team, Response):
        return team

    if team.status != Team.Status.ACTIVE:
        return Response(
            {"detail": "현재 참여할 수 없는 팀입니다."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return team


def _get_team(code):
    try:
        return Team.objects.get(code=code)
    except Team.DoesNotExist:
        return Response(
            {"detail": "존재하지 않는 팀 코드입니다."},
            status=status.HTTP_404_NOT_FOUND,
        )


def _get_admin_team(request, code):
    team = _get_team(code)
    if isinstance(team, Response):
        return team
    if team.owner_id != request.user.id:
        return Response({"detail": "팀 생성자만 관리자 기능을 사용할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)
    return team
