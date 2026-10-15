import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import type { PersonSummary } from "@/types";

interface PeopleToMeetListProps {
  people: PersonSummary[];
}

export function PeopleToMeetList({ people }: PeopleToMeetListProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">People to meet</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-4">
          {people.map((person) => (
            <li key={person.id} className="space-y-1">
              <p className="text-sm font-medium">{person.name}</p>
              <p className="text-xs text-muted-foreground">{person.role}</p>
              {person.expertise.length > 0 ? (
                <ul className="flex flex-wrap gap-1 pt-1">
                  {person.expertise.map((item) => (
                    <li
                      key={item}
                      className="rounded border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground"
                    >
                      {item}
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}