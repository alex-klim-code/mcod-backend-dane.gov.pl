import mimetypes
import os

import falcon
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET

from mcod.resources.models import ResourceFile


class AEDMediaSink:
    """Serve private-bucket files only through published MCOD resources."""

    def __call__(self, request, response):
        if request.method not in ("GET", "HEAD"):
            raise falcon.HTTPMethodNotAllowed(["GET", "HEAD"])
        path = request.path
        prefix = settings.MEDIA_URL.rstrip("/") + "/resources/"
        if not path.startswith(prefix):
            raise falcon.HTTPNotFound
        file_name = path[len(prefix) :]
        resource_file = (
            ResourceFile.objects.select_related("resource__dataset")
            .filter(
                file=file_name,
                is_main=True,
                resource__status="published",
                resource__dataset__status="published",
            )
            .first()
        )
        if not resource_file:
            raise falcon.HTTPNotFound
        resource_file.file.open("rb")
        response.stream = resource_file.file
        response.content_length = resource_file.file.size
        response.content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        response.set_header(
            "Content-Disposition",
            'attachment; filename="{}"'.format(os.path.basename(file_name).replace('"', "")),
        )
        response.status = falcon.HTTP_200


@require_GET
@login_required
def aed_resource_media_view(request, path):
    """Serve resource files in Django admin after authenticating a staff user."""
    file_name = path
    resource_file = (
        ResourceFile.objects.select_related("resource__dataset")
        .filter(file=file_name, is_main=True)
        .first()
    )
    if not resource_file:
        raise Http404
    if not (
        request.user.is_staff
        and request.user.has_perm("resources.change_resource")
    ) and not (
        resource_file.resource.status == "published"
        and resource_file.resource.dataset.status == "published"
    ):
        raise Http404
    resource_file.file.open("rb")
    return FileResponse(
        resource_file.file,
        as_attachment=True,
        filename=os.path.basename(file_name),
    )
