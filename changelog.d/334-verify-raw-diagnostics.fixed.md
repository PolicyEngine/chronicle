Make `chronicle verify-raw` classify Wrangler diagnostics more carefully.
Colour codes are now stripped before matching, so a missing object is still
reported as `missing_remote` when Wrangler colours words inside the message. A
marker now counts only as a whole phrase, and only on a line that holds nothing
but markers or that reports an error. So a marker inside a longer identifier,
or on a line that reports no error, now gives `fetch_error`. An error line that
merely mentions a marker (for example
`error: could not reach bucket; NoSuchKey handling disabled`) is still
classified as `missing_remote`. Both statuses are failures, and neither change
can produce `verified`.
