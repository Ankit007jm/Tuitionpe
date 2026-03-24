"""
TuitionPe — File upload utility.

Uses Cloudinary when CLOUDINARY_URL env var is set (production on Render),
falls back to local disk otherwise (local development).
"""

import os
import io


def upload_image(file, filename):
    """
    Upload an image file.  Returns a Cloudinary secure URL (production)
    or a local relative path like "uploads/filename.jpg" (development).

    :param file:     A Werkzeug FileStorage object.
    :param filename: The sanitised filename to use.
    """
    file_bytes = file.read()

    if os.environ.get('CLOUDINARY_URL'):
        import cloudinary.uploader
        public_id = os.path.splitext(filename)[0]   # strip extension
        result = cloudinary.uploader.upload(
            io.BytesIO(file_bytes),
            folder='tuitionpe',
            public_id=public_id,
            overwrite=True,
            resource_type='auto',
        )
        return result['secure_url']

    # ── Local fallback ────────────────────────────────────────
    from flask import current_app
    upload_dir = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_dir, exist_ok=True)
    with open(os.path.join(upload_dir, filename), 'wb') as f:
        f.write(file_bytes)
    return f"uploads/{filename}"
