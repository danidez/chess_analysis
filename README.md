# Chess Game Analysis: Do Opening Advantages Actually Win Lower-Rated Games?

A data science project testing whether small opening-phase evaluation edges predict outcomes in amateur chess, using Stockfish-annotated Lichess games. Built as part of a Data Science degree at UNIVESP.

> **Status:** In progress. Core pipeline and H1 analysis are complete; H2/H3 results are pending a revision on statistics.

## Motivation

A common belief among club-level players is that opening preparation is crucial to win a game of chess and will give you a modest edge out of the opening (say, +0.8 to +1.2 pawns per Stockfish) and by that is a meaningful predictor of who wins. This project puts that belief to the test statistically, and asks what *actually* decides games below 1800 Elo: the opening, or what happens later on the board.

## Hypotheses

- **H1** — A small opening-phase evaluation advantage (~0.8–1.2 pawns) does **not** strongly predict game outcome at lower ratings.
- **H2** — Games are decided more by large mid/late-game evaluation swings than by opening edges.
- **H3** — Blunder frequency and magnitude correlate more strongly with outcome than the opening evaluation does.

Scope: games with average Elo below 1800 and time controls of 5+ minutes.

## Data

Sourced from monthly [Lichess database dumps](https://database.lichess.org/) with native Stockfish evaluations, filtered for adequate eval coverage before inclusion. Sampling is done with a PowerShell-orchestrated pipeline (`curl.exe` + 7-Zip) to pull and decompress a manageable slice of a given month's dump.

## Methodology

1. **Parsing** — PGNs are parsed with `python-chess`, pulling structured `PovScore` evaluations from annotated dumps.
2. **Feature engineering** — Each game is reduced to a single row: player Elos, time control, ply count, first-advantage ply, opening eval, which side held the advantage, blunder counts/sizes, largest evaluation swing, and the ply where the game was effectively decided.
3. **Modeling** — Logistic regression (`statsmodels`, formula API) is used to relate these features to game outcome.
   - **H1** is scoped to games where the opening eval sits in the 0.8–1.2 pawn band, framed from the advantage-holder's perspective.
   - **H2/H3** use all decisive games with no opening-eval restriction, framed from White's perspective.
4. **Diagnostics** — Pseudo-R², likelihood-ratio tests, and VIF checks for multicollinearity accompany each model.

## Results so far

| Hypothesis | Finding |
|---|---|
| H1 | Pseudo-R² ≈ 2.34e-05, LLR p = 0.319 — no meaningful relationship between a small opening edge and outcome. |
| H2/H3 | Pseudo-R² increases substantially once blunder variables are added to a swing-only model; VIF confirms no multicollinearity issue between swing and blunder features. |

H2/H3 results are provisional pending a revision.

## Tech stack

Python · `python-chess` · `statsmodels` · `pandas` / `numpy` · `matplotlib`

## About the author

Built by Daniel, a Data Science student and competitive chess player, also a volunteer chess instructor — this project sits at the intersection of both.
