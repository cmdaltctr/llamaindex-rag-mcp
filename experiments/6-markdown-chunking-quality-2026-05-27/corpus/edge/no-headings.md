The most overlooked engineering skill is the willingness to read the source code of
the libraries you depend on. Most bugs you will hit in production are not in your code,
they are in the seam between your code and somebody else's, and you cannot reason about
that seam without reading both sides of it. Nobody teaches this in school and almost
nobody writes blog posts about it because it is not glamorous, but it is the difference
between an engineer who can ship and an engineer who escalates every other ticket to a
vendor support queue.

Reading library source code is an acquired taste. The first time you crack open a real
codebase — Django, React, Rails, FastAPI, the Linux kernel, anything that has been
actively developed for more than five years — you will be overwhelmed. The patterns
will be unfamiliar, the abstractions will feel arbitrary, and the comments will assume
context you do not have. Push through it anyway. Pick a single function that is
misbehaving in your application, and trace it inward. Most of the time the bug is
exactly where you suspected, and most of the time the fix is one or two lines, and
most of the time the maintainers will accept your patch if it comes with a test. The
culture of open source is overwhelmingly welcoming to first-time contributors who put
in the effort to read the code before they file the issue.

The second-most overlooked skill is patience with build systems. Every modern stack
spends an embarrassing fraction of its developer-hours on build configuration, and
everyone hates it, and everyone keeps doing it because the alternatives are worse.
Webpack, Vite, esbuild, Rollup, Bun, Cargo, Maven, Gradle, Bazel, Make, CMake, Meson —
the names change every five years, but the problems are eternal. Dependency resolution,
incremental compilation, source maps, hot reload, deployment artefacts. If you ignore
the build system, the build system will not ignore you. The senior engineer on your
team is not the one who writes the most clever feature code; it is the one who fixed
the build last week so the rest of the team could ship.

The third-most overlooked skill is observability discipline. Logging is easy and
useless. Metrics are harder and more useful. Distributed tracing is harder still and
nearly indispensable for any system that fans out across more than two services. The
temptation when an outage happens is to add more logging, but more logging is almost
always a mistake. The right move is to figure out what question you wished you could
answer during the outage, and instrument the system to answer that question next time.
If your post-mortem ends with "we should add more logging", you have not actually
learned anything. If it ends with "we should add a metric called request-queue-depth
exported by the API gateway", you have done the work.

Programming languages do not matter as much as people think. Most production systems
are limited by the database, the network, the disk, the cache, the operating system, or
the humans who operate them, not by the language they are written in. The choice of
language does matter for ergonomics, for ecosystem, for hiring, and for long-term
maintainability, but it almost never matters for performance unless you are running at
a scale where you have a dedicated platform team. People argue about Rust versus Go
versus Python versus TypeScript as if the choice were existential. It almost never is.
The team that ships in a language they understand will outperform the team that ships
in a language that is theoretically faster but operationally unfamiliar.

The last and hardest skill is knowing when to delete code. Every codebase accumulates
features that nobody uses, configuration flags that nobody remembers, abstractions that
turned out not to pay for themselves, and dependencies that have become liabilities. The
temptation is always to leave them in place — they work, deleting them is risky, and
the team has more important things to do. The temptation is wrong. Code that nobody
reads is code that nobody understands, and code that nobody understands is code that
breaks at the worst possible moment in a way that takes three days to debug. Delete
aggressively. Delete the dead feature flag. Delete the abstraction that has only one
implementation. Delete the dependency that does one thing you could write in twenty
lines. Your future self will thank you, and so will whoever inherits the codebase
after you.

None of this is novel. Every senior engineer you have ever worked with knows it, and
if you ask them they will tell you the same things in slightly different words. The
reason it is worth writing down is that the industry rewards novelty over discipline,
and the books and conference talks are mostly about novelty, and the disciplines that
actually keep production systems running are mostly transmitted as oral tradition
inside individual teams. If you are early in your career, find a senior engineer who
is willing to mentor you and copy everything they do for two years. If you are late in
your career, find a junior engineer who deserves the same and pass it along. The
industry trains itself one apprenticeship at a time, and the apprenticeships are the
only part of the training that has held up across forty years of churning fashion.
