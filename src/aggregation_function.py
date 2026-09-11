import chess.pgn
from src.config import DATA_RAW, DATA_PROCESSED

# --- tunable thresholds, keep as constants so they're easy to justify/change later ---
BLUNDER_THRESHOLD_CP = 200      # eval swing >= this counts as a blunder
DECISIVE_THRESHOLD_CP = 300     # |eval| that marks the game as "basically decided"
ADV_LOW_CP, ADV_HIGH_CP = 80, 120   # your 0.8–1.2 pawn advantage band
OPENING_WINDOW_PLY = 28         # through move 14 (both sides) = ply 28
MATE_CAP_CP = 2000              # any mate score gets capped to this magnitude

def get_cp(node) -> int | None:
    """Extract centipawn eval (White's perspective) from a node's structured eval, if present."""
    score = node.eval()  # PovScore or None
    if score is None:
        return None
    white_score = score.white()               # Score relative to White
    return white_score.score(mate_score=MATE_CAP_CP)  # int, mate scores capped automatically


def eval_to_cp(cp, mate_in):
    """Unify cp and mate scores into one signed centipawn value."""
    if cp is not None:
        return cp
    if mate_in is not None:
        sign = 1 if mate_in > 0 else -1
        return sign * MATE_CAP_CP
    return None

def parse_game_features(game: chess.pgn.Game, game_id: str, min_eval_coverage=0.5):
    evals = []
    for ply, node in enumerate(game.mainline(), start=1):
        cp = get_cp(node)
        evals.append({
            "ply": ply,
            "side": "white" if ply % 2 == 1 else "black",
            "cp": cp,
        })

    num_plies = len(evals)
    if num_plies == 0:
        return None

    # --- NEW: require the game to actually have eval data ---
    num_with_eval = sum(1 for e in evals if e["cp"] is not None)
    eval_coverage = num_with_eval / num_plies
    if eval_coverage < min_eval_coverage:
        return None

    # --- opening advantage: first ply within window where |eval| lands in [0.8, 1.2] ---
    first_adv_ply, opening_eval, adv_holder = None, None, "none"
    for e in evals:
        if e["ply"] > OPENING_WINDOW_PLY:
            break
        if e["cp"] is None:
            continue
        if ADV_LOW_CP <= abs(e["cp"]) <= ADV_HIGH_CP:
            first_adv_ply = e["ply"]
            opening_eval = e["cp"] / 100.0
            adv_holder = "white" if e["cp"] > 0 else "black"
            break

    num_blunders_white = 0
    num_blunders_black = 0
    first_blunder_ply = None
    largest_swing_cp = 0  # will store the SIGNED value now
    largest_swing_abs = 0  # helper for comparison

    prev_cp = None
    for e in evals:
        if e["cp"] is None:
            continue
        if prev_cp is not None:
            swing = e["cp"] - prev_cp  # signed, White's perspective
            mover = e["side"]

            is_blunder = (
                    (mover == "white" and swing <= -BLUNDER_THRESHOLD_CP) or
                    (mover == "black" and swing >= BLUNDER_THRESHOLD_CP)
            )
            if is_blunder:
                if mover == "white":
                    num_blunders_white += 1
                else:
                    num_blunders_black += 1
                if first_blunder_ply is None:
                    first_blunder_ply = e["ply"]

            if abs(swing) > largest_swing_abs:
                largest_swing_abs = abs(swing)
                largest_swing_cp = swing  # keep the SIGN, drop the "side" concept

        prev_cp = e["cp"]

    # --- decisive moment: first ply after which |eval| stays >= threshold for the rest of the game ---
    decisive_moment_ply = None
    last_below_ply = None
    for e in reversed(evals):
        if e["cp"] is not None and abs(e["cp"]) < DECISIVE_THRESHOLD_CP:
            last_below_ply = e["ply"]
            break
    for e in evals:
        if e["cp"] is None:
            continue
        if (last_below_ply is None or e["ply"] > last_below_ply) and abs(e["cp"]) >= DECISIVE_THRESHOLD_CP:
            decisive_moment_ply = e["ply"]
            break

    # --- headers / outcome ---
    h = game.headers
    try:
        avg_elo = (int(h.get("WhiteElo")) + int(h.get("BlackElo"))) / 2
    except (TypeError, ValueError):
        avg_elo = None

    result = h.get("Result")
    outcome_map_white = {"1-0": "win", "0-1": "loss", "1/2-1/2": "draw"}
    outcome_map_black = {"0-1": "win", "1-0": "loss", "1/2-1/2": "draw"}
    if adv_holder == "white":
        adv_holder_outcome = outcome_map_white.get(result)
    elif adv_holder == "black":
        adv_holder_outcome = outcome_map_black.get(result)
    else:
        adv_holder_outcome = None

    return {
        "game_id": game_id,
        "white": h.get("White"),
        "black": h.get("Black"),
        "white_elo": h.get("WhiteElo"),
        "black_elo": h.get("BlackElo"),
        "avg_elo": avg_elo,
        "time_control": h.get("TimeControl"),
        "num_plies": num_plies,
        "first_adv_ply": first_adv_ply,
        "opening_eval": opening_eval,
        "adv_holder": adv_holder,
        "result": result,
        "adv_holder_outcome": adv_holder_outcome,
        "num_blunders_white": num_blunders_white,
        "num_blunders_black": num_blunders_black,
        "first_blunder_ply": first_blunder_ply,
        "largest_swing": largest_swing_cp / 100.0,
        "decisive_moment_ply": decisive_moment_ply,
    }

import pandas as pd

def base_time_seconds(tc: str):
    """'300+3' -> 300. Returns None if malformed."""
    if not tc or "+" not in tc:
        return None
    try:
        return int(tc.split("+")[0])
    except ValueError:
        return None


def build_games_table(pgn_path, min_base_seconds=300, max_avg_elo=1800, min_plies=20, limit=None):
    rows = []
    stats = {"total": 0, "no_eval": 0, "too_short": 0, "elo_filtered": 0, "time_filtered": 0, "kept": 0}

    with open(pgn_path, encoding="utf-8", errors="ignore") as f:
        i = 0
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            i += 1
            if limit and i > limit:
                break
            stats["total"] += 1

            game_id = f"g{i}"
            try:
                feats = parse_game_features(game, game_id)
            except Exception as e:
                print(f"Skipping {game_id}: {e}")
                continue

            if feats is None:
                stats["no_eval"] += 1
                continue
            if feats["num_plies"] < min_plies:
                stats["too_short"] += 1
                continue
            if feats["avg_elo"] is None or feats["avg_elo"] >= max_avg_elo:
                stats["elo_filtered"] += 1
                continue
            base = base_time_seconds(feats["time_control"])
            if base is None or base < min_base_seconds:
                stats["time_filtered"] += 1
                continue

            stats["kept"] += 1
            rows.append(feats)

    print(stats)
    return pd.DataFrame(rows)


games_df = build_games_table(DATA_RAW / "lichess_partial/lichess_2026-07_partial.pgn")
games_df.to_parquet(DATA_PROCESSED / "games_features.parquet")
print(games_df.shape)
print(games_df.head())
