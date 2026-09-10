//! checkerz — interactive benchmark capability TUI (ratatui).
//!
//! Offline viewer over `docs/data/benchmarks.json` (the bcheck snapshot).
//! Refresh data with `bcheck --fetch`; this binary never networks.

mod app;
mod export;
mod model;
mod scoring;
mod staleness;
mod ui;

use app::{partition_matched, App, SortKey};
use std::io::IsTerminal;
use std::path::{Path, PathBuf};

fn print_help() {
    println!(
        "checkerz — interactive benchmark capability TUI\n\
         \n\
         Usage: checkerz [--data PATH] [-n N|--top N] [--all] [--plain] [--fetch]\n\
         \n\
         Options:\n  \
         --data PATH   benchmarks snapshot (default: docs/data/benchmarks.json)\n  \
         -n, --top N   limit to top N models (default: 50, 0 = unlimited)\n  \
         --all         include all evaluated models (default: tri-verified 3/3 only)\n  \
         --plain       accepted for CLI parity; colors follow the terminal\n  \
         --fetch       NOT SUPPORTED here — run `bcheck --fetch` to refresh cache\n  \
         -h, --help    this help"
    );
}

/// Locate `docs/data/benchmarks.json` from cwd / ancestors / executable dir.
fn resolve_data_path(arg: Option<&str>) -> Option<PathBuf> {
    if let Some(a) = arg {
        let p = PathBuf::from(a);
        if p.exists() {
            return Some(p);
        }
        eprintln!("checkerz: --data {a} not found");
        std::process::exit(2);
    }
    let mut dirs = vec![std::env::current_dir().ok()?];
    if let Ok(exe) = std::env::current_exe() {
        dirs.extend(exe.ancestors().skip(1).take(4).map(|p| p.to_path_buf()));
    }
    let mut anc = std::env::current_dir().ok()?;
    for _ in 0..4 {
        dirs.push(anc.clone());
        if !anc.pop() {
            break;
        }
    }
    for d in &dirs {
        let p = d.join("docs/data/benchmarks.json");
        if p.exists() {
            return Some(p);
        }
        // Running from inside checkerz/ itself.
        let p = d.join("../docs/data/benchmarks.json");
        if p.exists() {
            return Some(p);
        }
    }
    None
}

fn parse_top(args: &[String], i: &mut usize) -> usize {
    *i += 1;
    if *i >= args.len() {
        eprintln!("checkerz: --top needs a number");
        std::process::exit(2);
    }
    match args[*i].parse::<i64>() {
        Ok(n) if n >= 0 => n as usize,
        _ => {
            eprintln!("checkerz: --top needs a non-negative integer");
            std::process::exit(2);
        }
    }
}

fn main() -> anyhow::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let mut data_arg: Option<String> = None;
    let mut top: usize = 50;
    let mut tri_only = true;
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "-h" | "--help" => {
                print_help();
                return Ok(());
            }
            "--data" => {
                i += 1;
                if i >= args.len() {
                    eprintln!("checkerz: --data needs a path");
                    std::process::exit(2);
                }
                data_arg = Some(args[i].clone());
            }
            s if s.starts_with("--data=") => {
                data_arg = Some(s["--data=".len()..].to_string());
            }
            "-n" | "--top" => top = parse_top(&args, &mut i),
            "--all" => tri_only = false,
            "--plain" => {}
            "--fetch" | "--refresh" => {
                eprintln!("checkerz: --fetch is not supported by the viewer — run `bcheck --fetch` to refresh docs/data/raw/ + benchmarks.json, then relaunch checkerz.");
                std::process::exit(2);
            }
            other => {
                eprintln!("checkerz: unknown argument {other} (see --help)");
                std::process::exit(2);
            }
        }
        i += 1;
    }

    let data_path = resolve_data_path(data_arg.as_deref()).unwrap_or_else(|| {
        eprintln!("checkerz: docs/data/benchmarks.json not found (pass --data PATH)");
        std::process::exit(2);
    });
    let snapshot = model::load_snapshot(&data_path)?;
    let raw_dir = data_path
        .parent()
        .map(|p| p.join("raw"))
        .unwrap_or_else(|| Path::new("docs/data/raw").to_path_buf());
    let stale_note = staleness::cache_staleness_note(&raw_dir);
    let (matched, unmatched) = partition_matched(snapshot.models);
    let mut app = App::new(matched, unmatched, tri_only, top, stale_note);

    if !std::io::stdin().is_terminal() || !std::io::stdout().is_terminal() {
        println!("{}", ui::render_text(&app));
        return Ok(());
    }

    run_tty(&mut app, &data_path)
}

fn reports_dir(data_path: &Path) -> PathBuf {
    data_path
        .parent()
        .and_then(|d| d.parent())
        .map(|docs| docs.join("reports"))
        .unwrap_or_else(|| PathBuf::from("docs/reports"))
}

#[allow(clippy::too_many_lines)]
fn run_tty(app: &mut App, data_path: &Path) -> anyhow::Result<()> {
    use crossterm::{
        event::{self, Event, KeyCode, KeyModifiers},
        execute,
        terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
    };
    use ratatui::{backend::CrosstermBackend, Terminal};

    enable_raw_mode()?;
    let mut stdout = std::io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let result: anyhow::Result<()> = (|| {
        loop {
            terminal.draw(|f| ui::draw(f, app))?;
            if !event::poll(std::time::Duration::from_millis(100))? {
                continue;
            }
            let Event::Key(key) = event::read()? else { continue };
            if key.kind != event::KeyEventKind::Press {
                continue;
            }
            let code = key.code;
            let shift = key.modifiers.contains(KeyModifiers::SHIFT);

            // --- search typing mode ---
            if app.searching {
                match code {
                    KeyCode::Enter => app.commit_search(),
                    KeyCode::Esc => app.cancel_search(),
                    KeyCode::Backspace => app.pop_search_char(),
                    KeyCode::Char(c) if !key.modifiers.contains(KeyModifiers::CONTROL) && !key.modifiers.contains(KeyModifiers::ALT) && c.is_ascii_graphic() || c == ' ' => {
                        app.push_search_char(c);
                    }
                    _ => {}
                }
                continue;
            }

            // --- modal interactions shadow everything else ---
            if app.any_modal() {
                match code {
                    KeyCode::Esc | KeyCode::Char('q') | KeyCode::Char('Q') => app.close_modals(),
                    _ if app.inspecting => match code {
                        KeyCode::Enter | KeyCode::Char(' ') => app.inspecting = false,
                        KeyCode::Char('j') | KeyCode::Down => app.move_cursor(1),
                        KeyCode::Char('k') | KeyCode::Up => app.move_cursor(-1),
                        KeyCode::Char('n') | KeyCode::Char(']') | KeyCode::PageDown => app.next_page(),
                        KeyCode::Char('p') | KeyCode::Char('[') | KeyCode::PageUp => app.prev_page(),
                        _ => {}
                    },
                    _ if app.showing_diff => match code {
                        KeyCode::Char('d') | KeyCode::Char('D') | KeyCode::Enter | KeyCode::Char(' ') => {
                            app.showing_diff = false;
                        }
                        KeyCode::Char('b') | KeyCode::Char('B') => app.pin_baseline(),
                        KeyCode::Char('j') | KeyCode::Down => app.move_cursor(1),
                        KeyCode::Char('k') | KeyCode::Up => app.move_cursor(-1),
                        _ => {}
                    },
                    _ if app.showing_roles => match code {
                        KeyCode::Char('r') | KeyCode::Char('R') | KeyCode::Enter | KeyCode::Char(' ') => {
                            app.showing_roles = false;
                        }
                        _ => {}
                    },
                    _ if app.showing_help => match code {
                        KeyCode::Char('?') | KeyCode::Enter | KeyCode::Char(' ') => {
                            app.showing_help = false;
                        }
                        _ => {}
                    },
                    _ => {}
                }
                continue;
            }

            // --- normal mode ---
            match code {
                KeyCode::Char('j') | KeyCode::Down => app.move_cursor(1),
                KeyCode::Char('k') | KeyCode::Up => app.move_cursor(-1),
                KeyCode::Char('n') | KeyCode::Char(']') | KeyCode::PageDown => app.next_page(),
                KeyCode::Char('p') | KeyCode::Char('[') | KeyCode::PageUp => app.prev_page(),
                KeyCode::Home | KeyCode::Char('g') => {
                    app.cursor = 0;
                    app.page = 0;
                }
                KeyCode::End | KeyCode::Char('G') => {
                    if !app.filtered.is_empty() {
                        app.cursor = app.filtered.len() - 1;
                        app.page = app.cursor / app.page_size;
                    }
                }
                KeyCode::Enter | KeyCode::Char(' ') => {
                    if !app.filtered.is_empty() {
                        app.inspecting = true;
                    }
                }
                KeyCode::Char('R') => app.showing_roles = true,
                KeyCode::Char('d') | KeyCode::Char('D') => {
                    if !app.filtered.is_empty() {
                        app.showing_diff = true;
                    }
                }
                KeyCode::Char('b') | KeyCode::Char('B') => app.pin_baseline(),
                KeyCode::Char('?') => app.showing_help = true,
                KeyCode::Char('e') | KeyCode::Char('E') => app.toggle_tri(),
                KeyCode::Char('P') => app.toggle_pareto(),
                KeyCode::Char('c') | KeyCode::Char('C') => app.set_sort(SortKey::Coding),
                KeyCode::Char('r') => app.set_sort(SortKey::Reasoning),
                KeyCode::Char('s') => app.set_sort(SortKey::Speed),
                KeyCode::Char('x') | KeyCode::Char('X') => app.set_sort(SortKey::Ctx),
                KeyCode::Char('$') => app.set_sort(SortKey::Price),
                KeyCode::Char('v') | KeyCode::Char('V') => app.set_sort(SortKey::Avi),
                KeyCode::Char('S') | KeyCode::Char('o') | KeyCode::Char('O') => app.cycle_sort(),
                KeyCode::Tab => app.cycle_pool(),
                KeyCode::Char(c @ '1'..='6') => {
                    let idx = (c as u8 - b'1') as usize;
                    if idx < app::POOLS.len() {
                        app.pool = app::POOLS[idx].to_string();
                        app.page = 0;
                        app.cursor = 0;
                        app.apply_filters();
                        app.status = format!("Pool: {}", app::pool_label(&app.pool));
                    }
                }
                KeyCode::Char('/') => app.enter_search(),
                KeyCode::Esc => app.reset_filters(),
                KeyCode::Char('m') | KeyCode::Char('M') => {
                    let p = reports_dir(data_path).join("benchmarks.md");
                    match export::atomic_write(&p, &export::render_markdown(app)) {
                        Ok(()) => app.status = format!("Exported Markdown -> {}", p.display()),
                        Err(e) => app.status = format!("Export failed: {e}"),
                    }
                }
                KeyCode::Char('h') | KeyCode::Char('H') => {
                    let p = reports_dir(data_path).join("benchmarks.html");
                    match export::atomic_write(&p, &export::render_html(app)) {
                        Ok(()) => app.status = format!("Exported HTML -> {}", p.display()),
                        Err(e) => app.status = format!("Export failed: {e}"),
                    }
                }
                KeyCode::Char('q') | KeyCode::Char('Q') => break,
                _ => {
                    // Shift+4 yields '$' already; plain '4' with shift flag on some terms:
                    if shift && code == KeyCode::Char('4') {
                        app.set_sort(SortKey::Price);
                    }
                }
            }
        }
        Ok(())
    })();

    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;
    result
}
