from django.urls import path

from .views import (
    TeamAnnouncementView,
    ClaimResetView,
    MyAssignmentView,
    MyTeamListView,
    ParticipantClaimView,
    TeamAdminDashboardView,
    TeamCreateView,
    TeamDetailView,
    TeamLeaderboardView,
    TeamLeaderboardVisitView,
    TeamEndView,
    TeamCountdownView,
    TeamPlannedEndView,
    TeamRevealModeView,
    TeamRulesView,
    TeamResultView,
    TeamResultReleaseView,
    UnclaimedParticipantListView,
)


urlpatterns = [
    path("", TeamCreateView.as_view(), name="team-create"),
    path("mine/", MyTeamListView.as_view(), name="team-mine"),
    path("<str:code>/", TeamDetailView.as_view(), name="team-detail"),
    path("<str:code>/leaderboard/", TeamLeaderboardView.as_view(), name="team-leaderboard"),
    path("<str:code>/leaderboard/visit/", TeamLeaderboardVisitView.as_view(), name="team-leaderboard-visit"),
    path("<str:code>/unclaimed/", UnclaimedParticipantListView.as_view(), name="team-unclaimed"),
    path("<str:code>/claim/", ParticipantClaimView.as_view(), name="participant-claim"),
    path("<str:code>/my-assignment/", MyAssignmentView.as_view(), name="my-assignment"),
    path("<str:code>/result/", TeamResultView.as_view(), name="team-result"),
    path("<str:code>/countdown/", TeamCountdownView.as_view(), name="team-countdown"),
    path("<str:code>/admin/dashboard/", TeamAdminDashboardView.as_view(), name="team-admin-dashboard"),
    path("<str:code>/admin/planned-end/", TeamPlannedEndView.as_view(), name="team-planned-end"),
    path("<str:code>/admin/reveal-mode/", TeamRevealModeView.as_view(), name="team-reveal-mode"),
    path("<str:code>/admin/rules/", TeamRulesView.as_view(), name="team-rules"),
    path("<str:code>/admin/announcement/", TeamAnnouncementView.as_view(), name="team-announcement"),
    path("<str:code>/admin/reset-claim/", ClaimResetView.as_view(), name="claim-reset"),
    path("<str:code>/admin/end/", TeamEndView.as_view(), name="team-end"),
    path("<str:code>/admin/release-results/", TeamResultReleaseView.as_view(), name="team-result-release"),
]
