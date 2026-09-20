from django.db import models


class Sandbox(models.Model):
    name = models.CharField(max_length=120)
    syllabus = models.FileField(upload_to="syllabi/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Topic(models.Model):
    sandbox = models.ForeignKey(Sandbox, related_name="topics", on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    x = models.FloatField(null=True, blank=True)
    y = models.FloatField(null=True, blank=True)
    tags = models.ManyToManyField(Tag, related_name="topics", blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name


class Prerequisite(models.Model):
    sandbox = models.ForeignKey(Sandbox, related_name="prerequisites", on_delete=models.CASCADE)
    prerequisite = models.ForeignKey(Topic, related_name="unlocks", on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic, related_name="requires", on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["prerequisite", "topic"], name="unique_prerequisite_edge"),
        ]


class Document(models.Model):
    sandbox = models.ForeignKey(Sandbox, related_name="documents", on_delete=models.CASCADE)
    file = models.FileField(upload_to="documents/")
    name = models.CharField(max_length=255)
    topics = models.ManyToManyField(Topic, related_name="documents", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class VideoJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued"
        GENERATING_SCRIPT = "generating_script"
        GENERATING_AUDIO = "generating_audio"
        RENDERING = "rendering"
        DONE = "done"
        FAILED = "failed"

    sandbox = models.ForeignKey(Sandbox, related_name="video_jobs", on_delete=models.CASCADE)
    topic_ids = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    video = models.FileField(upload_to="videos/", blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
