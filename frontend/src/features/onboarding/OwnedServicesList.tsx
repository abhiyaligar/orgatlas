import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import type { OwnedService } from "@/types";

const CRITICALITY_STYLES: Record<string, string> = {
  critical: "bg-red-500/15 text-red-300 border-red-500/30",
  high: "bg-amber-500/15 text-amber-200 border-amber-500/30",
  medium: "bg-sky-500/15 text-sky-200 border-sky-500/30",
  low: "bg-slate-500/15 text-slate-300 border-slate-500/30",
};

interface OwnedServicesListProps {
  services: OwnedService[];
  onSelect?: (serviceId: string) => void;
}

export function OwnedServicesList({ services, onSelect }: OwnedServicesListProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Services owned</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-3">
          {services.map((service) => (
            <li key={service.id} className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                {onSelect ? (
                  <button
                    type="button"
                    onClick={() => onSelect(service.id)}
                    className="text-sm font-medium underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  >
                    {service.name}
                  </button>
                ) : (
                  <span className="text-sm font-medium">{service.name}</span>
                )}
                <Badge
                  variant="outline"
                  className={CRITICALITY_STYLES[service.criticality] ?? CRITICALITY_STYLES.low}
                >
                  {service.criticality}
                </Badge>
              </div>
              {service.description ? (
                <p className="text-xs text-muted-foreground">{service.description}</p>
              ) : null}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}