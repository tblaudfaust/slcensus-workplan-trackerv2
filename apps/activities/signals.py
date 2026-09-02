"""Custom signals fired explicitly by apps.activities.services / views and
by the upload pipeline, rather than relying on post_save introspection --
this way every sender already knows exactly which fields changed and by
whom, which a generic post_save receiver can't reconstruct on its own."""

import django.dispatch

activity_created = django.dispatch.Signal()  # kwargs: activity, changed_by, source
activity_changed = django.dispatch.Signal()  # kwargs: activity, changed_fields, changed_by, source
