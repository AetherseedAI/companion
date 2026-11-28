# Proton Mail through Bridge, on the unit

Errands read and send email over IMAP and SMTP. For Proton Mail that means
Proton Mail Bridge, run on the unit itself, listening on 127.0.0.1 only.

## What is known

- Bridge needs a paid Proton Mail plan (Proton's own support page).
- Proton ships Bridge for x86-64 Linux only. On a Raspberry Pi it is built from
  Proton's source (github.com/ProtonMail/proton-bridge, `make build-nogui`).
  Version 3.27.2 builds for arm64 against Debian 13's libfido2, libsecret and
  OpenSSL, which a unit already has, and runs on one (`bridge --version`).
- Bridge keeps its login in a keychain. Headless, that is `pass` with a GPG key
  of its own and no passphrase.
- Bridge listens on 127.0.0.1: IMAP 1143, SMTP 1025, STARTTLS with a
  certificate it made for itself. The email connector upgrades to TLS when
  Bridge offers it and does not check that certificate, since the connection
  never leaves the device. Mail servers off the unit are checked as always.
- The firewall lets only the companion's user out. Bridge runs as a user of
  its own, so it needs its own two lines (DNS and 443). That is the owner's
  step.

## What is not known yet

- Whether Bridge accepts a login before STARTTLS on loopback. The connector
  does STARTTLS whenever it is offered, so either way works.
- How Bridge behaves over weeks on a unit (memory, sync of a large mailbox).

## Steps

The kit: `bridge`, `proton-bridge`, `SHA256SUMS`, `debs/` (pass, tree) and
`proton_bridge_setup.sh`. The script installs and prints the rest: the
firewall lines, the login (the owner types the Proton password and code), and
what goes in the console under Errands > Email.

A built-from-source copy does not update itself: turn automatic updates off in
the CLI and replace it by hand when Proton releases a new version.
