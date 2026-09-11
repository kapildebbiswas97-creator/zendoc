# Document Extraction Boundary v1

ZENDOC separates medical-document text extraction from OCR and from clinical imaging interpretation.

## Working now

`native_utf8_text` supports bounded, authorized extraction from UTF-8 `.txt` medical documents stored through the existing record-storage abstraction. Extracted text is normalized on demand, hashed with SHA-256, returned only to an authorized requester, and is not automatically converted into verified medical facts.

## Integration required

OCR for PDF, PNG, JPG/JPEG, DOC, and DOCX remains `INTEGRATION_REQUIRED`. When OCR is unavailable, ZENDOC returns an explicit integration-required state instead of inventing document text.

## Disabled

Clinical imaging interpretation for X-ray, CT, MRI, ultrasound and general imaging remains `DISABLED`. A future imaging pipeline requires a separately validated specialist model, clinical evaluation, provenance, human governance and an explicit product/regulatory review. Native extraction of a radiology text report must never be represented as interpretation of the underlying image.

## Privacy and authorization

All report access reuses the existing Health Memory `reports` authorization/consent boundary. Cross-patient access fails closed. Extracted text is not written to ordinary logs and v1 does not persist an additional plaintext extraction copy; report metadata stores only extraction state, hash and character-count information.
