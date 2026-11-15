# Stage 2 (the tarpit): a call for collaborators

**English** ・ [日本語](../stage2.md)

Stage 1 of sanadamaru (decoy doors, bait keys, records and blocking) stops at identifying who touched a door.

For stage 2 we are exploring a tarpit: leading the visitors who touched a door into an endless fake maze, so that their AI agents waste compute and time. AI-driven attackers follow what they read, search everything, and pay for compute at every step. The question is whether that behavior can be turned into a defense.

Before building anything, we are looking for people to help design it.

## Why we have not built it yet

- A maze costs the defender something too. Slowing the attacker down while slowing your own service down defeats the purpose.
- We first need to confirm that it can stay inside [the lines sanadamaru never crosses](lines.md), especially "never run anything on the visitor's machine".
- We have not settled on a way to measure whether it works.

## Prior work

- Cloudflare's AI Labyrinth (March 2025): leads AI crawlers that ignore robots.txt into a maze of AI-generated fake pages. [Cloudflare blog](https://blog.cloudflare.com/ai-labyrinth/)
- Nepenthes (January 2025): traps AI training crawlers in an endless maze of links. [404 Media](https://www.404media.co/developer-creates-infinite-maze-to-trap-ai-crawlers-in/)

What would set sanadamaru's stage 2 apart is that only visitors who touched a door ever enter the maze. Ordinary crawlers and users never wander in.

## Conditions (every proposal must meet all of them)

1. Stay inside every one of [the lines](lines.md). In particular, run nothing on the visitor's machine (no zip bombs, heavy scripts or borrowed compute). Maze content is plain text only.
2. Only sources that touched a door enter the maze. Real users, search engines and health checks never do.
3. The defender's cost has clear limits (concurrent connections, time per connection, bytes sent, compute).
4. Off by default. Even when on, it quietly falls back to stage 1 (403) when a limit is reached.
5. Its effect can be counted from the records (how many times, and how much was spent in the maze).
6. Maze pages show no realistic personal data and no other company's key formats.

## Open questions

- How should the maze pages be generated? Using AI on the defender's side to write them costs the defender compute too. Can they be assembled from fixed material instead?
- Respond slowly (a classic tarpit) or respond with a lot? Which costs the defender less and the attacker more?
- How far may we play on an AI agent's tendency to read and follow instructions? Is it inside the lines to give the attacking AI instructions in the maze text?
- How do we measure the effect?
- What legal questions need checking (for example, whether this could count as interfering with someone's business)?

## How to take part

- Start with an issue that describes your idea and how it meets the conditions above. Please send code pull requests only after the design is settled.
- Do not post techniques that target real services in public. If you find a loophole, report it as described in [SECURITY.md](../../SECURITY.md).
