`build-bundle` writes and counts each source package's consumer rows as it reads
them, and frees them before it builds the next package. It used to hold every
package's rows until the end. CI's merged default bundle (1.74M rows) peaked at
15.0 GiB that way and now peaks at 3.4 GiB; the UK suite's local build went from
12.8 to 4.0 GiB. `consumer_facts.jsonl`, `coverage.json`, `source_packages.json`
and the build report are unchanged (byte-identical on the UK suite); the facts
file takes its name only once every package is in it.
