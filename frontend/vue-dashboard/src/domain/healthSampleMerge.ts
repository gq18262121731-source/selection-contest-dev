import type { HealthSample } from "../api/client";

function hasFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function preferPositiveNumber(
  previous: number | null | undefined,
  incoming: number | null | undefined,
): number {
  if (hasFiniteNumber(incoming) && incoming > 0) return incoming;
  if (hasFiniteNumber(previous)) return previous;
  return hasFiniteNumber(incoming) ? incoming : 0;
}

function preferOptionalPositiveNumber(
  previous: number | null | undefined,
  incoming: number | null | undefined,
): number | null | undefined {
  if (!hasFiniteNumber(incoming)) return previous ?? undefined;
  if (incoming > 0) return incoming;
  if (previous !== null && previous !== undefined) return previous;
  return incoming;
}

function preferIncrementalInt(
  previous: number | null | undefined,
  incoming: number | null | undefined,
): number | undefined {
  if (!hasFiniteNumber(incoming)) return previous ?? undefined;
  if (incoming > 0) return Math.round(incoming);
  if (previous !== null && previous !== undefined) return previous;
  return Math.round(incoming);
}

function normalizeBloodPressure(value?: string | null): string | undefined {
  if (!value) return undefined;
  const [sbpRaw, dbpRaw] = value.split("/", 2);
  const sbp = Number.parseInt(sbpRaw ?? "", 10);
  const dbp = Number.parseInt(dbpRaw ?? "", 10);
  if (!Number.isFinite(sbp) || !Number.isFinite(dbp)) return undefined;
  if (sbp <= 0 || dbp <= 0) return undefined;
  return `${sbp}/${dbp}`;
}

export function mergeHealthSample(
  previous: HealthSample | null | undefined,
  incoming: HealthSample | null | undefined,
): HealthSample | null {
  if (!incoming) return previous ?? null;
  if (!previous) return incoming;

  return {
    ...previous,
    ...incoming,
    device_mac: incoming.device_mac || previous.device_mac,
    timestamp: incoming.timestamp || previous.timestamp,
    heart_rate: preferPositiveNumber(previous.heart_rate, incoming.heart_rate),
    blood_oxygen: preferPositiveNumber(previous.blood_oxygen, incoming.blood_oxygen),
    temperature: preferPositiveNumber(previous.temperature, incoming.temperature),
    ambient_temperature: preferOptionalPositiveNumber(previous.ambient_temperature ?? null, incoming.ambient_temperature ?? null),
    surface_temperature: preferOptionalPositiveNumber(previous.surface_temperature ?? null, incoming.surface_temperature ?? null),
    blood_pressure: normalizeBloodPressure(incoming.blood_pressure) ?? normalizeBloodPressure(previous.blood_pressure),
    battery: preferIncrementalInt(previous.battery ?? null, incoming.battery ?? null),
    steps: preferIncrementalInt(previous.steps ?? null, incoming.steps ?? null),
    health_score: preferIncrementalInt(previous.health_score ?? null, incoming.health_score ?? null),
    sos_flag: incoming.sos_flag ?? previous.sos_flag ?? false,
    sos_value: incoming.sos_value ?? previous.sos_value ?? null,
    sos_trigger: incoming.sos_trigger ?? previous.sos_trigger ?? null,
    source: incoming.source ?? previous.source,
    packet_type: incoming.packet_type ?? previous.packet_type ?? null,
    device_uuid: incoming.device_uuid ?? previous.device_uuid ?? null,
  };
}

export function mergeHealthSeries(samples: HealthSample[]): HealthSample[] {
  return [...samples]
    .sort((left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime())
    .reduce<HealthSample[]>((merged, sample) => {
      const previous = merged[merged.length - 1];
      const next = mergeHealthSample(previous, sample) ?? sample;
      if (previous && previous.timestamp === sample.timestamp) {
        merged[merged.length - 1] = next;
      } else {
        merged.push(next);
      }
      return merged;
    }, []);
}
