"use client";

import { useState } from "react";
import { fetchInfo, type VideoInfo } from "@/lib/api";
import { Workspace } from "./Workspace";
import styles from "./Tool.module.css";

type State =
  | { status: "idle" | "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; url: string; info: VideoInfo };

export function Tool() {
  const [state, setState] = useState<State>({ status: "idle" });
  const loading = state.status === "loading";

  const load = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const url = String(new FormData(event.currentTarget).get("url")).trim();
    setState({ status: "loading" });
    try {
      setState({ status: "ready", url, info: await fetchInfo(url) });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Something went wrong.";
      setState({ status: "error", message });
    }
  };

  return (
    <div className={`${styles.page} ${state.status === "ready" ? styles.compact : ""}`}>
      <header className={`${styles.bar} ${state.status === "ready" ? styles.editorBar : ""}`}>
        <span className={styles.mark}>Clipper</span>
        {state.status === "ready" && <div id="editor-header-actions" className={styles.editorHeaderActions} />}
      </header>

      <main className={styles.main}>
        {state.status === "ready" ? (
          <Workspace key={state.info.id} info={state.info} url={state.url} />
        ) : (
          <section className={styles.landingHero} aria-label="Load a video">
            <div className={styles.heroContent}>
              <div className={styles.hero}>
                <p className={styles.eyebrow}>YOUTUBE CLIPPER</p>
                <h1>
                  <span>Take only the</span>
                  <span>part you need.</span>
                </h1>
                <p className={styles.description}>Paste a YouTube link, choose your moment,<br className={styles.desktopBreak} /> and download the clip.</p>
              </div>

              <form className={styles.form} onSubmit={load}>
                <label className={styles.srOnly} htmlFor="youtube-url">YouTube URL</label>
                <span className={styles.inputIcon} aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none">
                    <path d="M9.5 14.5 14.5 9.5M7.25 17.75l-1 1a3.18 3.18 0 0 1-4.5-4.5l3.5-3.5a3.18 3.18 0 0 1 4.5 0" />
                    <path d="m16.75 6.25 1-1a3.18 3.18 0 0 1 4.5 4.5l-3.5 3.5a3.18 3.18 0 0 1-4.5 0" />
                  </svg>
                </span>
                <input
                  id="youtube-url"
                  name="url"
                  type="url"
                  required
                  autoFocus
                  placeholder="Paste YouTube link…"
                  aria-label="YouTube link"
                />
                <button type="submit" className={styles.submit} disabled={loading} aria-label={loading ? "Loading video" : "Load video"}>
                  <span aria-hidden="true">{loading ? "…" : "→"}</span>
                </button>
              </form>
              <p className={styles.microcopy}>
                <span><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m13 2-8 12h6l-1 8 8-12h-6l1-8Z" /></svg>Fast</span>
                <span><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3" y="4" width="18" height="13" rx="1" /><path d="M8 21h8M12 17v4" /></svg>Up to 4K</span>
                <span><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m20.5 13.5-7 7-10-10v-7h7l10 10Z" /><circle cx="7.5" cy="7.5" r="1" /></svg>No watermark</span>
              </p>

              {loading && (
                <div className={styles.loading} role="status">
                  <strong>LOADING VIDEO</strong>
                  <span>This won’t take long.</span>
                  <div className={styles.loadingLine} aria-hidden />
                </div>
              )}
              {state.status === "error" && <p role="alert" className={styles.error}>{state.message}</p>}
            </div>
            <ClippingPreview />
          </section>
        )}
      </main>

      <footer className={styles.footer}>
        Simple. Fast. Powerful.
      </footer>
    </div>
  );
}

function ClippingPreview() {
  return (
    <div className={styles.visual} aria-hidden="true">
      <p className={styles.visualCaption}>EXTRACT<br />THE MOMENTS<br />THAT MATTER.</p>
      <div className={styles.visualStage}>
        <div className={styles.stack}>
          <span className={styles.outlineFrame} />
          <span className={`${styles.outlineFrame} ${styles.outlineFrameSecond}`} />
          <div className={styles.thumbnails}>
            <span /><span /><span />
          </div>
          <div className={styles.mainFrame}>
            <span className={styles.framePlaceholder}>VIDEO PREVIEW</span>
            <span className={styles.playButton}><span /></span>
            <div className={styles.frameControls}>
              <div className={styles.frameControlMeta}>
                <span className={styles.framePlayIcon} aria-hidden="true" />
                <span>0:42 / 2:18</span>
              </div>
              <div className={styles.frameTrack} aria-hidden="true">
                <span className={styles.frameTrackSelected} />
                <span className={`${styles.frameHandle} ${styles.frameHandleStart}`} />
                <span className={`${styles.frameHandle} ${styles.frameHandleEnd}`} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
