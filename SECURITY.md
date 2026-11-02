# Security

LiquidFrame is a development preview intended for a single operating-system user on localhost. Do not expose the helper through a public bind address, reverse proxy, or shared network. Authentication is a local browser session; private-view passcodes do not encrypt source files.

Report suspected vulnerabilities privately to the repository maintainer through a private security advisory if the published repository enables it. Until a private reporting destination exists, request a private contact without publishing exploit details, credentials, paths, passcodes, database files, or personal media. No public reporting inbox is currently configured in this local project.

Useful report details: affected version, platform, minimal reproduction using synthetic/public fixtures, impacted boundary, and suggested mitigation. Security-sensitive areas include origin/session checks, folder confinement/symlinks, private-view authorization, decoder/delegate restrictions, model downloads/checksums, and replacement/restore integrity.

Only the current development version is maintained. Dependency updates must pass the processing and privacy tests. Optional native decoders have their own update and security requirements. A local-only design reduces network exposure but does not protect against other software with access to your user account.
