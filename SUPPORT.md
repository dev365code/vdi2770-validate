# Support

The software is free and stays free, and there is no paid tier of the judgement
itself: a free run and a supported run give the same result on the same file.

Professional support is available for the work around it — update guarantees
when the sources change, backports to a version you have frozen, help with
embedding, and change-impact notes for your product.

## Where to ask

Open an issue on this repository for anything this tool got wrong: a verdict
that looks wrong, a file it refused, or this tool failing on a file. The issue
template asks for what the next section describes.

Two pages may answer it first. If the reference implementation judged the same
file differently, [docs/divergences.md](docs/divergences.md) says where the two
disagree and why. If this tool said nothing about something,
[docs/scope.md](docs/scope.md) says what it does not do, deliberately, and the
known limits of what it does.

What does not fit a public page — a commercial enquiry, a licensing question, a
file you can share only privately — goes to zero8004paz@gmail.com.

## What to attach

The diagnostic bundle, not the file. `vdi2770-validate check YOUR-FILE
--bug-report` writes it where you ran the check and sends nothing. It carries
the shape of the file and what the run said by rule code, and nothing from the
file; [SECURITY.md](SECURITY.md) lists what it carries and what it does not.
Read it before you attach it: `--show-bundle` prints all of it and writes
nothing. When this tool stops on a file with an error of its own, it writes the
same bundle without being asked, and says so.

Do not attach the file itself, since an issue is public. Say what you expected
and what this tool said, and whether we may ask you for the file privately.

## Security reports

Open a GitHub security advisory on this repository — a reproduction archive
helps there, and if it cannot be shared, a description of its structure will
do. A problem that is not sensitive can be an ordinary issue, and a malformed
container that produces a confusing message is one. [SECURITY.md](SECURITY.md)
says what is defended, where the proof of each defence is, and how a security
fix is announced.
