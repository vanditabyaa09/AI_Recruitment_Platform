import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { JobDescription } from "@/lib/api";

export function ParsedJDPreview({ jd }: { jd: JobDescription | null }) {
  if (!jd?.parsed_data) return null;

  const data = jd.parsed_data as Record<string, unknown>;
  const hardSkills = (data.hard_skills as string[]) || [];
  const softSkills = (data.soft_skills as string[]) || [];
  const mustHave = (data.must_have as string[]) || [];
  const niceToHave = (data.nice_to_have as string[]) || [];
  const domain = (data.domain_knowledge as string[]) || [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Parsed Job Requirements</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="flex flex-wrap gap-2">
          {Boolean(data.role) && (
            <Badge variant="default">{String(data.role)}</Badge>
          )}
          {Boolean(data.seniority) && (
            <Badge variant="secondary">{String(data.seniority)}</Badge>
          )}
          {Boolean(data.experience_required) && (
            <Badge variant="secondary">{String(data.experience_required)} experience</Badge>
          )}
        </div>

        {hardSkills.length > 0 && (
          <div>
            <p className="mb-1 font-medium text-slate-700">Hard Skills</p>
            <div className="flex flex-wrap gap-1">
              {hardSkills.map((s) => (
                <Badge key={s} variant="secondary">{s}</Badge>
              ))}
            </div>
          </div>
        )}

        {softSkills.length > 0 && (
          <div>
            <p className="mb-1 font-medium text-slate-700">Soft Skills</p>
            <div className="flex flex-wrap gap-1">
              {softSkills.map((s) => (
                <Badge key={s} variant="secondary">{s}</Badge>
              ))}
            </div>
          </div>
        )}

        {mustHave.length > 0 && (
          <div>
            <p className="mb-1 font-medium text-slate-700">Must Have</p>
            <ul className="list-disc space-y-0.5 pl-5 text-slate-600">
              {mustHave.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        )}

        {niceToHave.length > 0 && (
          <div>
            <p className="mb-1 font-medium text-slate-700">Nice to Have</p>
            <ul className="list-disc space-y-0.5 pl-5 text-slate-600">
              {niceToHave.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        )}

        {domain.length > 0 && (
          <div>
            <p className="mb-1 font-medium text-slate-700">Domain Knowledge</p>
            <div className="flex flex-wrap gap-1">
              {domain.map((d) => (
                <Badge key={d} variant="secondary">{d}</Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
