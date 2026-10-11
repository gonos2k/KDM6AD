# Preflight attempt 1

The first metadata-only preflight saved the public `20250720/05` listing XML, then failed in the local XML namespace parser before writing a plan or downloading any observation data. The response was valid S3 `ListBucketResult` XML (`KeyCount=480`, `IsTruncated=false`). No granule request, model, RTTOV/H/K, M, or optimizer call occurred. The helper was corrected to use the response's default XML namespace; the saved listing bytes are reused unchanged by the next preflight. The executed helper SHA-256 was not captured before that local fix.
