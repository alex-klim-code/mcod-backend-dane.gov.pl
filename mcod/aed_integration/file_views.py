import mimetypes

import falcon

from mcod.aed_integration.views import _mapping_or_404, secure
from mcod.resources.models import ResourceFile


class AEDResourceFileView:
    @secure
    def on_get(self, request, response, external_organization_id, resource_id, file_id=None):
        mapping = _mapping_or_404(external_organization_id)
        files = ResourceFile.objects.filter(
            resource_id=resource_id,
            resource__is_removed=False,
            resource__is_permanently_removed=False,
            resource__dataset__is_removed=False,
            resource__dataset__is_permanently_removed=False,
            resource__dataset__organization_id=mapping.organization_id,
            resource__dataset__aed_integration_mapping__organization_mapping=mapping,
        )
        item = files.filter(pk=file_id).first() if file_id is not None else files.filter(is_main=True).first()
        if not item:
            raise falcon.HTTPNotFound
        try:
            stream = item.file.open("rb")
        except FileNotFoundError:
            raise falcon.HTTPNotFound(description="The stored file is missing.")
        response.content_type = mimetypes.guess_type(item.file.name)[0] or "application/octet-stream"
        response.downloadable_as = item.file.name.rsplit("/", 1)[-1]
        response.stream = stream
