`build-bundle` writes and counts each source package's consumer rows as it reads
them, and frees them before it builds the next package. It used to hold every
package's rows until the end, so the merged default bundle's 1.66M rows peaked
at 15.4 GB on CI's 16 GB runner, and a bundle a fifth larger no longer fit.
`consumer_facts.jsonl`, `coverage.json` and the build report are unchanged; the
facts file takes its name only once every package is in it.
