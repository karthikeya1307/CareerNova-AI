import { Link } from "react-router-dom";
import Badge from "../../../components/ui/Badge";
import { humanize } from "../../dashboard/format";
import ScoreRing from "../../dashboard/components/ScoreRing";
import { categoryLabel, formatScore, scoreTone } from "../interviewFormat";

// Results of a completed session: the backend's summary (complete_session), shown as returned.
// The overall score is the backend's: the average over ALL questions, unanswered ones counting as 0.
export default function SessionSummary({ session }) {
  const s = session.summary || {};
  const overall = s.overall_score ?? session.score;
  const categories = Object.entries(s.by_category || {});
  return (
    <section aria-labelledby="results-title" className="flex flex-col gap-5">
      <h2 id="results-title" className="text-base font-semibold text-slate-900">
        Results
      </h2>
      <div className="flex flex-wrap items-center gap-5">
        {overall != null && <ScoreRing value={overall} label="overall score" />}
        <dl className="grid flex-1 grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          <div className="rounded-lg bg-slate-50 p-2.5">
            <dt className="text-xs text-slate-500">Overall</dt>
            <dd className="font-semibold text-slate-900">
              {formatScore(overall)}/100 {s.label ? <Badge tone={scoreTone(overall)}>{s.label}</Badge> : null}
            </dd>
          </div>
          <div className="rounded-lg bg-slate-50 p-2.5">
            <dt className="text-xs text-slate-500">Answered</dt>
            <dd className="font-semibold text-slate-900">
              {s.answered ?? session.answered_count}/{s.total ?? session.total_questions}
            </dd>
          </div>
          {s.average_answered_score != null && (
            <div className="rounded-lg bg-slate-50 p-2.5">
              <dt className="text-xs text-slate-500">Average of answered</dt>
              <dd className="font-semibold text-slate-900">{formatScore(s.average_answered_score)}/100</dd>
            </div>
          )}
        </dl>
      </div>
      {s.unanswered_count_as_zero && <p className="text-xs text-slate-500">Unanswered questions count as 0 in the overall score. Scores are automated practice guidance, not a hiring decision.</p>}

      {categories.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-700">By category</h3>
          <ul className="mt-2 flex flex-wrap gap-2" aria-label="Scores by category">
            {categories.map(([c, score]) => (
              <li key={c}>
                <Badge tone={scoreTone(score)}>
                  {categoryLabel(c)}: {formatScore(score)}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <h3 className="text-sm font-medium text-slate-700">Strengths</h3>
          {s.strengths?.length ? (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-mint-900" aria-label="Strengths">
              {s.strengths.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-slate-500">No answers scored 65 or more in this session.</p>
          )}
        </div>
        <div>
          <h3 className="text-sm font-medium text-slate-700">Areas to improve</h3>
          {s.improvements?.length ? (
            <ul className="mt-2 flex flex-col gap-2 text-sm" aria-label="Areas to improve">
              {s.improvements.map((item, i) => (
                <li key={i} className="rounded-lg bg-amber-50 p-2.5 text-amber-950">
                  <p className="font-medium">
                    {item.question} <span className="font-normal">({formatScore(item.score)}/100)</span>
                  </p>
                  {item.focus?.length > 0 && <p className="mt-0.5 text-xs">Focus on: {item.focus.join("; ")}</p>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-slate-500">No answered question scored below 65.</p>
          )}
        </div>
      </div>

      {s.related_skill_gaps?.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-700">Keep preparing</h3>
          <p className="text-xs text-slate-500">Skills from this session that are on your learning plan:</p>
          <ul className="mt-2 flex flex-wrap gap-2" aria-label="Related skill gaps">
            {s.related_skill_gaps.map((g) => (
              <li key={g.recommendation_id}>
                <Badge tone="info">
                  {g.skill} · {humanize(g.status)}
                </Badge>
              </li>
            ))}
          </ul>
          <Link to="/skill-gaps" className="mt-2 inline-block text-sm font-medium text-brand-700 hover:underline">
            Open your learning plan
          </Link>
        </div>
      )}
    </section>
  );
}
