Make source-package discovery find nested package members, such as
`stats_nz/census_2023_family_type/rc_01`, not just `<source>/<package>`
directories. The alias-drift guard and the default-bundle coverage check rely on
discovery, so a nested member that lost its alias is now reported instead of
being silently left out. Symlinked directories are followed at every depth
(the old two-level glob followed them at its two levels), and a link back into
its own ancestry ends the walk. Also correct the `verify-raw` diagnostics docstring: an
error line that merely mentions a missing-object marker still counts as
missing.
