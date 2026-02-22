// Supabase Edge Function: GDACS RSS Poller
// Runs on a cron schedule (every 15 min) to poll GDACS for new disaster alerts
// and insert them into the ingested_events table.
//
// Deploy: supabase functions deploy notify-disaster
// Cron:   Add to supabase/config.toml or via Dashboard → Edge Functions → Schedules

import { serve } from "https://deno.land/std@0.177.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

// GDACS alert level → our severity
const SEVERITY_MAP: Record<string, string> = {
  Red: "critical",
  Orange: "high",
  Green: "medium",
};

// GDACS event type → our disaster type
const TYPE_MAP: Record<string, string> = {
  EQ: "earthquake",
  TC: "hurricane",
  FL: "flood",
  VO: "volcano",
  DR: "drought",
  WF: "wildfire",
  TS: "tsunami",
};

interface GDACSItem {
  external_id: string;
  event_type: string;
  title: string;
  description: string;
  severity: string;
  latitude: number | null;
  longitude: number | null;
  location_name: string;
  raw_payload: Record<string, unknown>;
}

serve(async (req: Request) => {
  try {
    // Supabase client with service role for writes
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    // 1. Fetch GDACS RSS feed
    const feedUrl = "https://www.gdacs.org/xml/rss.xml";
    const feedResp = await fetch(feedUrl, {
      headers: { "User-Agent": "DisasterMgmt-EdgeFunction/1.0" },
    });

    if (!feedResp.ok) {
      throw new Error(`GDACS fetch failed: ${feedResp.status}`);
    }

    const xmlText = await feedResp.text();

    // 2. Parse XML (Deno has DOMParser built-in)
    const parser = new DOMParser();
    const doc = parser.parseFromString(xmlText, "application/xml");
    const items = doc?.querySelectorAll("item") ?? [];

    // 3. Get GDACS source ID
    const { data: sourceRows } = await supabase
      .from("external_data_sources")
      .select("id")
      .eq("source_name", "gdacs")
      .limit(1);

    const sourceId = sourceRows?.[0]?.id;
    if (!sourceId) {
      throw new Error("GDACS source not found in external_data_sources");
    }

    // 4. Parse items
    const parsed: GDACSItem[] = [];
    for (const item of items) {
      const title = item.querySelector("title")?.textContent?.trim() ?? "";
      const description =
        item.querySelector("description")?.textContent?.trim() ?? "";
      const link = item.querySelector("link")?.textContent?.trim() ?? "";
      const pubDate = item.querySelector("pubDate")?.textContent?.trim() ?? "";

      // GDACS namespaced elements
      const eventType =
        item.getElementsByTagNameNS("http://www.gdacs.org", "eventtype")[0]
          ?.textContent ?? "";
      const alertLevel =
        item.getElementsByTagNameNS("http://www.gdacs.org", "alertlevel")[0]
          ?.textContent ?? "";
      const eventId =
        item.getElementsByTagNameNS("http://www.gdacs.org", "eventid")[0]
          ?.textContent ?? "";

      const latText =
        item.getElementsByTagNameNS(
          "http://www.w3.org/2003/01/geo/wgs84_pos#",
          "lat"
        )[0]?.textContent ?? null;
      const lonText =
        item.getElementsByTagNameNS(
          "http://www.w3.org/2003/01/geo/wgs84_pos#",
          "long"
        )[0]?.textContent ?? null;

      const lat = latText ? parseFloat(latText) : null;
      const lon = lonText ? parseFloat(lonText) : null;

      // Only ingest Orange / Red alerts
      if (!["Orange", "Red"].includes(alertLevel)) continue;

      parsed.push({
        external_id: `gdacs-${eventType}-${eventId}`,
        event_type: "gdacs_alert",
        title,
        description,
        severity: SEVERITY_MAP[alertLevel] ?? "medium",
        latitude: lat,
        longitude: lon,
        location_name: title,
        raw_payload: {
          link,
          pub_date: pubDate,
          gdacs_event_type: eventType,
          gdacs_alert_level: alertLevel,
          gdacs_event_id: eventId,
          disaster_type_mapped: TYPE_MAP[eventType] ?? "other",
        },
      });
    }

    // 5. Deduplicate and insert
    let insertedCount = 0;
    for (const event of parsed) {
      // Check if already exists
      const { data: existing } = await supabase
        .from("ingested_events")
        .select("id")
        .eq("external_id", event.external_id)
        .limit(1);

      if (existing && existing.length > 0) continue;

      const { error } = await supabase.from("ingested_events").insert({
        source_id: sourceId,
        ...event,
        ingested_at: new Date().toISOString(),
      });

      if (!error) insertedCount++;
    }

    // 6. Update source status
    await supabase
      .from("external_data_sources")
      .update({
        last_polled_at: new Date().toISOString(),
        last_status: "success",
        last_error: null,
      })
      .eq("source_name", "gdacs");

    // 7. For critical events, call the backend batch prediction endpoint
    const criticalEvents = parsed.filter((e) => e.severity === "critical");
    if (criticalEvents.length > 0) {
      const backendUrl =
        Deno.env.get("BACKEND_URL") ?? "http://localhost:8000";
      for (const evt of criticalEvents) {
        try {
          await fetch(`${backendUrl}/api/ingestion/poll/gdacs`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
          });
        } catch {
          // Backend may not be reachable from edge function; that's OK,
          // the backend's own GDACS poller will pick it up.
        }
      }
    }

    return new Response(
      JSON.stringify({
        success: true,
        parsed: parsed.length,
        inserted: insertedCount,
        critical: criticalEvents.length,
      }),
      { headers: { "Content-Type": "application/json" } }
    );
  } catch (error) {
    console.error("GDACS Edge Function error:", error);

    // Update source status with error
    try {
      const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
      const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
      const supabase = createClient(supabaseUrl, supabaseServiceKey);
      await supabase
        .from("external_data_sources")
        .update({
          last_polled_at: new Date().toISOString(),
          last_status: "error",
          last_error: String(error).slice(0, 500),
        })
        .eq("source_name", "gdacs");
    } catch {
      // ignore
    }

    return new Response(
      JSON.stringify({ success: false, error: String(error) }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
});
