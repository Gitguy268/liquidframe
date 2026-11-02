/* Modified for the local LiquidFrame companion on 2026-10-17. See LIQUIDFRAME.md. */
"use client";
import { useEffect, useState } from "react";
import { Alert, Box, Button, Link, Typography } from "@mui/material";
import { useBook } from "@/context/BookContext";
import { BOOK_FORMAT_CHOICES, type BookFormatId } from "@/lib/bookFormats";

type Handoff = { library: string; selection: { ids?: string[]; selection_id?: string; exclude_ids?: string[] } };
export default function LiquidFrameImport() {
  const { addPhotos, processingPhotos, appView, setAppView, photos, bookFormat, setBookFormat } = useBook();
  const [handoff, setHandoff] = useState<Handoff | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (!location.hash.startsWith("#import=")) return;
    try {
      const value = JSON.parse(decodeURIComponent(location.hash.slice(8)));
      if (typeof value.library !== "string" || !value.selection) throw new Error();
      setHandoff(value);
    } catch { setError("The library selection could not be read. Select the photos again in LiquidFrame."); }
    history.replaceState(null, "", location.pathname);
  }, []);
  async function importSelection() {
    if (!handoff || busy) return;
    setBusy(true); setError("");
    try {
      const query = "?library=" + encodeURIComponent(handoff.library);
      const response = await fetch("/api/v1/photobook/selection" + query, {
        method: "POST", headers: { "Content-Type": "application/json", "X-Openphoto": "1" },
        body: JSON.stringify({ selection: handoff.selection }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Cannot read this selection.");
      const files: File[] = [];
      let totalBytes = 0;
      for (const [index, photo] of data.photos.entries()) {
        setMessage(`Preparing photo ${index + 1} of ${data.photos.length}…`);
        const image = await fetch("/api/v1/photobook/photos/" + encodeURIComponent(photo.id) + query);
        if (!image.ok) throw new Error("A selected photo is no longer available. Return to LiquidFrame and check the selection.");
        const blob = await image.blob();
        totalBytes += blob.size;
        if (totalBytes > 256 * 1024 * 1024) throw new Error("These photo copies exceed 256 MB. Select fewer photos and try again.");
        files.push(new File([blob], photo.name, { type: "image/png", lastModified: Date.parse(photo.captured) || Date.now() }));
      }
      // Append to a restored book; never erase it without the user's action.
      await addPhotos(files, { replace: false });
      setHandoff(null); setMessage("");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not import the selection."); setMessage(""); }
    finally { setBusy(false); }
  }
  return <Box component="header" sx={{ p: 2, bgcolor: "#fff", flexShrink: 0, borderBottom: "1px solid #ddd", color: "#1a1c1d" }}>
    <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center" }}>
      <Link href="/">← LiquidFrame</Link>
      <Typography component="strong">Ente Photobook · Local edition</Typography>
      <Link href="/photobook/source.zip" download>Source &amp; license (AGPL-3.0)</Link>
      {photos.length > 0 && <>
        <label>Book format <select aria-label="Book format" value={bookFormat.id} disabled={busy || processingPhotos} onChange={e => setBookFormat(e.target.value as BookFormatId)}>{BOOK_FORMAT_CHOICES.map(format => <option key={format.id} value={format.id}>{format.label} · {format.dimensionsLabel}</option>)}</select></label>
        {appView !== "edit" && <Button disabled={busy || processingPhotos} onClick={() => setAppView("edit")}>Edit book</Button>}
        {appView !== "results" && <Button variant="contained" disabled={busy || processingPhotos} onClick={() => setAppView("results")}>Preview &amp; export</Button>}
        {appView !== "start" && <Button disabled={busy || processingPhotos} onClick={() => setAppView("start")}>Choose new photos</Button>}
      </>}
    </Box>
    <Typography variant="body2" sx={{ mt: 1 }}>Books and photo copies are saved in this browser, separately from your LiquidFrame library. Export a copy before clearing browser data.</Typography>
    {handoff && <Box sx={{ mt: 1 }}>
      <Typography variant="body2">Add the selected library photos to this book as edited PNG copies (up to 6000 px). Hidden items, trash and videos cannot be imported. Up to 100 photos at a time.</Typography>
      <Button disabled={busy || processingPhotos} onClick={importSelection}>Add selected photos to book</Button>
      <Button disabled={busy} onClick={() => setHandoff(null)}>Dismiss selection</Button>
    </Box>}
    {message && <Typography role="status">{message}</Typography>}
    {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
  </Box>;
}
