Lock certifi 2026.10.19, which removes the compromised eMudhra root "emSign ECC
Root CA - G3", so the httpx downloads of publisher artifacts and the Supabase
client stop trusting certificates issued under it.
