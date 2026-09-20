from django.urls import path

from . import views


urlpatterns = [
    path("sandboxes/", views.sandboxes, name="sandboxes"),
    path("sandboxes/<int:sandbox_id>/", views.sandbox_detail, name="sandbox-detail"),
    path("sandboxes/<int:sandbox_id>/graph/", views.sandbox_graph, name="sandbox-graph"),
    path("sandboxes/<int:sandbox_id>/topics/", views.sandbox_topics, name="sandbox-topics"),
    path("sandboxes/<int:sandbox_id>/tags/", views.apply_tag, name="apply-tag"),
    path("sandboxes/<int:sandbox_id>/prerequisites/", views.prerequisites, name="prerequisites"),
    path("sandboxes/<int:sandbox_id>/documents/", views.documents, name="documents"),
    path("sandboxes/<int:sandbox_id>/syllabus/", views.syllabus, name="syllabus"),
    path("topics/<int:topic_id>/quiz/", views.topic_quiz, name="topic-quiz"),
    path("documents/<int:document_id>/", views.document_detail, name="document-detail"),
    path("topics/<int:topic_id>/", views.topic_detail, name="topic-detail"),
    path("topics/<int:topic_id>/tags/<int:tag_id>/", views.remove_tag, name="remove-tag"),
    path("tags/", views.tags, name="tags"),
]
