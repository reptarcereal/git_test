// Date formatting helpers. Arizona observes MST year-round (no DST), so the
// IANA zone America/Phoenix is correct in every season.
const AZ_TZ = "America/Phoenix";

export const fmtAZDateTime = (iso: string): string =>
  new Date(iso).toLocaleString("en-US", {
    timeZone: AZ_TZ,
    dateStyle: "medium",
    timeStyle: "short",
  });

export const fmtAZDate = (iso: string): string =>
  new Date(iso).toLocaleDateString("en-US", {
    timeZone: AZ_TZ,
    month: "short",
    day: "numeric",
    year: "numeric",
  });
