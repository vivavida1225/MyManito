from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.teams.models import Participant, Team

from .serializers import (
    CollisionDecisionSerializer,
    EvaluationSerializer,
    QuizSettingsSerializer,
    ReferenceAnswerSerializer,
    SolutionDraftSerializer,
)
from .services import (
    QuizError,
    admin_quiz_payload,
    confirm_evaluation,
    confirm_reference_answer,
    decide_collision,
    participant_quiz_payload,
    remind_pending_quiz_participants,
    save_solution_draft,
    update_quiz_settings,
)


def _admin_team(request, code):
    team = get_object_or_404(Team, code=code)
    if team.owner_id != request.user.id:
        return None
    return team


def _participant_team(request, code):
    team = get_object_or_404(Team, code=code)
    if not Participant.objects.filter(team=team, claimed_by=request.user).exists():
        return None
    return team


def _quiz_error_response(error, *, conflict=False):
    return Response(
        {"detail": str(error)},
        status=status.HTTP_409_CONFLICT if conflict else status.HTTP_400_BAD_REQUEST,
    )


class AdminQuizView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, code):
        team = _admin_team(request, code)
        if team is None:
            return Response({"detail": "팀 관리자만 사용할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)
        return Response(admin_quiz_payload(team))

    def patch(self, request, code):
        team = _admin_team(request, code)
        if team is None:
            return Response({"detail": "팀 관리자만 사용할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)
        serializer = QuizSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            update_quiz_settings(team, serializer.validated_data)
        except QuizError as error:
            return _quiz_error_response(error)
        return Response(admin_quiz_payload(team))


class AdminQuizRoundDecisionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, code, round_id):
        team = _admin_team(request, code)
        if team is None:
            return Response({"detail": "팀 관리자만 사용할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)
        serializer = CollisionDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            round_obj = decide_collision(
                team,
                round_id,
                request.user,
                serializer.validated_data["decision"],
            )
        except QuizError as error:
            return _quiz_error_response(error)
        return Response({"round_id": round_obj.id, "decision": round_obj.collision_decision})


class AdminQuizRoundReminderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, code, round_id):
        team = _admin_team(request, code)
        if team is None:
            return Response({"detail": "팀 관리자만 사용할 수 있습니다."}, status=status.HTTP_403_FORBIDDEN)
        try:
            result = remind_pending_quiz_participants(team, round_id)
        except QuizError as error:
            return _quiz_error_response(error)
        return Response(result)


class ParticipantQuizView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, code):
        team = _participant_team(request, code)
        if team is None:
            return Response(
                {"detail": "본인 확인을 마친 참가자만 사용할 수 있습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            return Response(participant_quiz_payload(team, request.user))
        except QuizError as error:
            return _quiz_error_response(error)


class ReferenceAnswerConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, code, item_id):
        team = _participant_team(request, code)
        if team is None:
            return Response({"detail": "접근 권한이 없습니다."}, status=status.HTTP_403_FORBIDDEN)
        serializer = ReferenceAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = confirm_reference_answer(
                team, item_id, request.user, serializer.validated_data["answer"]
            )
        except QuizError as error:
            return _quiz_error_response(error, conflict="이미 다른" in str(error))
        return Response(
            {
                "item_id": item.id,
                "answer": item.reference_answer,
                "confirmed_at": item.reference_confirmed_at,
            }
        )


class SolutionDraftView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, code, item_id):
        team = _participant_team(request, code)
        if team is None:
            return Response({"detail": "접근 권한이 없습니다."}, status=status.HTTP_403_FORBIDDEN)
        serializer = SolutionDraftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = save_solution_draft(
                team, item_id, request.user, serializer.validated_data["answer"]
            )
        except QuizError as error:
            return _quiz_error_response(error)
        return Response(
            {
                "item_id": item.id,
                "draft": item.solution_draft,
                "saved_at": item.solution_draft_saved_at,
            }
        )


class EvaluationConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, code, item_id):
        team = _participant_team(request, code)
        if team is None:
            return Response({"detail": "접근 권한이 없습니다."}, status=status.HTTP_403_FORBIDDEN)
        serializer = EvaluationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = confirm_evaluation(
                team, item_id, request.user, serializer.validated_data["score"]
            )
        except QuizError as error:
            return _quiz_error_response(error, conflict="이미 다른" in str(error))
        return Response(
            {
                "item_id": item.id,
                "score": item.evaluation_score,
                "evaluated_at": item.evaluated_at,
                "settlement_kind": item.settlement_kind,
            }
        )
