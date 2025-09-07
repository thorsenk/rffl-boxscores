#!/usr/bin/env python3
"""
Build a simple static browser view for a boxscores CSV.

Usage:
  python scripts/build_live_view.py <csv_path> [out_dir]

Writes:
  <out_dir>/index.html
  <out_dir>/data.js                (window.BOXES = [...])
  <out_dir>/index.embedded.html    (self-contained; no data.js)

Then serve:
  python -m http.server -d <out_dir> 8000
  → open http://localhost:8000/
"""
import csv
import json
import os
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/build_live_view.py <csv_path> [out_dir]")
        sys.exit(2)

    csv_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("build/live")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Read CSV to list of dicts
    rows = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # Infer simple metadata
    weeks = sorted({r.get("week") for r in rows})
    teams = sorted({r.get("team_code") for r in rows if r.get("team_code")})

    # Write data.js
    data_js = out_dir / "data.js"
    with data_js.open("w", encoding="utf-8") as f:
        f.write("window.BOXES = ")
        json.dump(rows, f, ensure_ascii=False)
        f.write(";\n")
        f.write("window.META = ")
        json.dump({"weeks": weeks, "teams": teams}, f, ensure_ascii=False)
        f.write(";\n")

    # Write index.html (inline JS/CSS; loads data.js)
    index_html = out_dir / "index.html"
    index_html.write_text(
        """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>RFFL Live Scores Viewer</title>
    <style>
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 16px; }
      header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
      select, input[type="checkbox"] { font-size: 14px; padding: 4px; }
      table { border-collapse: collapse; width: 100%; font-size: 13px; }
      th, td { border: 1px solid #ddd; padding: 6px 8px; }
      th { background: #f6f6f6; position: sticky; top: 0; z-index: 1; }
      tbody tr:nth-child(odd) { background: #fafafa; }
      .pill { display: inline-block; background: #eef; color: #224; padding: 0 6px; border-radius: 8px; font-size: 12px; }
      .controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
      .muted { color: #666; font-size: 12px; }
    </style>
  </head>
  <body>
    <header>
      <h2 style="margin:0">RFFL Live Scores Viewer</h2>
      <span id="summary" class="muted"></span>
    </header>
    <div class="controls">
      <label>Week
        <select id="week"></select>
      </label>
      <label>Team
        <select id="team">
          <option value="">All</option>
        </select>
      </label>
      <label>
        <input type="checkbox" id="startersOnly" checked /> Starters only
      </label>
      <label>Search
        <input type="text" id="search" placeholder="player/team/slot" />
      </label>
    </div>
    <div style="margin:8px 0" class="muted">Click headers to sort.</div>

    <table id="tbl">
      <thead>
        <tr>
          <th data-k="week">Week</th>
          <th data-k="matchup">Matchup</th>
          <th data-k="team_code">Team</th>
          <th data-k="team_owner_1">Owner</th>
          <th data-k="team_projected_total">Team Proj</th>
          <th data-k="team_actual_total">Team Act</th>
          <th data-k="slot_type">Type</th>
          <th data-k="slot">Slot</th>
          <th data-k="player_name">Player</th>
          <th data-k="position">Pos</th>
          <th data-k="rs_projected_pf">Proj</th>
          <th data-k="rs_actual_pf">Act</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>

    <script src="data.js"></script>
    <script>
      const S = {
        sortKey: 'team_actual_total',
        sortDir: 'desc',
      };

      const elWeek = document.getElementById('week');
      const elTeam = document.getElementById('team');
      const elStarters = document.getElementById('startersOnly');
      const elSearch = document.getElementById('search');
      const elBody = document.querySelector('#tbl tbody');
      const elHead = document.querySelector('#tbl thead');
      const elSummary = document.getElementById('summary');

      function initControls() {
        // Weeks
        const weeks = (window.META?.weeks || []).filter(Boolean);
        elWeek.innerHTML = weeks.map(w => `<option value="${w}">${w}</option>`).join('');
        if (weeks.length) elWeek.value = weeks[0];

        // Teams
        const teams = (window.META?.teams || []);
        for (const t of teams) {
          const opt = document.createElement('option');
          opt.value = t; opt.textContent = t; elTeam.appendChild(opt);
        }

        elWeek.addEventListener('change', render);
        elTeam.addEventListener('change', render);
        elStarters.addEventListener('change', render);
        elSearch.addEventListener('input', render);

        // Sort handlers
        elHead.addEventListener('click', (e) => {
          const th = e.target.closest('th');
          if (!th) return;
          const k = th.dataset.k;
          if (!k) return;
          if (S.sortKey === k) {
            S.sortDir = (S.sortDir === 'asc') ? 'desc' : 'asc';
          } else {
            S.sortKey = k; S.sortDir = 'asc';
          }
          render();
        });
      }

      function cmp(a, b) {
        const k = S.sortKey;
        const dir = S.sortDir === 'asc' ? 1 : -1;
        const av = a[k];
        const bv = b[k];
        const na = Number(av), nb = Number(bv);
        if (!Number.isNaN(na) && !Number.isNaN(nb)) {
          return (na - nb) * dir;
        }
        return String(av).localeCompare(String(bv)) * dir;
      }

      function render() {
        const week = elWeek.value;
        const team = elTeam.value;
        const startersOnly = elStarters.checked;
        const q = elSearch.value.trim().toLowerCase();

        let data = window.BOXES || [];
        if (week) data = data.filter(r => String(r.week) === String(week));
        if (team) data = data.filter(r => r.team_code === team);
        if (startersOnly) data = data.filter(r => r.slot_type === 'starters');
        if (q) {
          data = data.filter(r => {
            const hay = `${r.team_code} ${r.player_name} ${r.slot} ${r.position} ${r.team_owner_1}`.toLowerCase();
            return hay.includes(q);
          });
        }

        data = data.slice().sort(cmp);

        elBody.innerHTML = data.map(r => `
          <tr>
            <td>${r.week}</td>
            <td>${r.matchup}</td>
            <td><span class="pill">${r.team_code||''}</span></td>
            <td>${r.team_owner_1||''}</td>
            <td style="text-align:right">${Number(r.team_projected_total).toFixed(2)}</td>
            <td style="text-align:right">${Number(r.team_actual_total).toFixed(2)}</td>
            <td>${r.slot_type}</td>
            <td>${r.slot}</td>
            <td>${r.player_name}</td>
            <td>${r.position||''}</td>
            <td style="text-align:right">${Number(r.rs_projected_pf).toFixed(2)}</td>
            <td style="text-align:right">${Number(r.rs_actual_pf).toFixed(2)}</td>
          </tr>
        `).join('');

        elSummary.textContent = `${data.length} rows • sorted by ${S.sortKey} (${S.sortDir})`;
      }

      initControls();
      render();
    </script>
  </body>
  </html>
        """,
        encoding="utf-8",
    )

    # Also write an embedded (self-contained) variant
    embedded = out_dir / "index.embedded.html"
    embedded.write_text(
        (
            index_html.read_text(encoding="utf-8")
            .replace('<script src="data.js"></script>', '')
            .replace('<script>', '<script>\nwindow.BOXES = ' + json.dumps(rows) + ';\nwindow.META = ' + json.dumps({"weeks": weeks, "teams": teams}) + ';\n')
        ),
        encoding="utf-8",
    )

    print(f"✅ Built live view to {out_dir}\n   - index.html + data.js\n   - index.embedded.html (open directly if needed)")


if __name__ == "__main__":
    main()
