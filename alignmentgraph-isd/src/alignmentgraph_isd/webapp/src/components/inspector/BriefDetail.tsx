import { JsonRoot } from './JsonTree'
import type { Brief } from '../../api/types'

// Mirrors DesignBrief's declared fields, so anything else in the object can be
// shown separately as an extra rather than silently blending in.
const TOP_LEVEL = [
  'id', 'title', 'user_message', 'domain', 'difficulty', 'duration',
  'target_audience', 'learning_goals', 'context', 'constraints', 'refinement_request',
]
const CONTEXT_FIELDS = [
  'duration', 'learning_environment', 'class_size', 'learner_age',
  'learner_education', 'learner_role', 'domain_expertise', 'prior_knowledge',
]
const CONSTRAINT_FIELDS = [
  'resources', 'budget', 'tech_requirements', 'assessment_type', 'accessibility', 'language',
]

export function BriefDetail({ brief }: { brief: Brief }) {
  const context = (brief.context ?? {}) as Record<string, unknown>
  const constraints = (brief.constraints ?? {}) as Record<string, unknown>
  const goals = (brief.learning_goals ?? []) as string[]

  // Scenario files carry keys the brief has no field for (`variant_type`,
  // `context.additional_context`); they survive import, so they are shown.
  const extras = Object.entries(brief).filter(([key]) => !TOP_LEVEL.includes(key))
  const contextExtras = Object.entries(context).filter(([key]) => !CONTEXT_FIELDS.includes(key))

  return (
    <div className="inspector-body">
      <div className="section-title">Program</div>
      <dl className="kv">
        {row('Title', brief.title)}
        {row('Id', brief.id)}
        {row('Domain', brief.domain)}
        {row('Difficulty', brief.difficulty)}
        {row('Duration', brief.duration)}
        {row('Audience', brief.target_audience)}
      </dl>

      {brief.user_message && (
        <>
          <div className="section-title">What the designer asked for</div>
          <div className="small">{String(brief.user_message)}</div>
        </>
      )}

      {goals.length > 0 && (
        <>
          <div className="section-title">Learning goals ({goals.length})</div>
          <ol className="goal-list" style={{ paddingLeft: 20 }}>
            {goals.map((goal, index) => <li key={index}>{goal}</li>)}
          </ol>
        </>
      )}

      <div className="section-title">Context</div>
      <dl className="kv">
        {CONTEXT_FIELDS.map((field) => row(humanise(field), context[field]))}
        {contextExtras.map(([key, value]) => row(humanise(key), value))}
      </dl>

      <div className="section-title">Constraints</div>
      <dl className="kv">
        {CONSTRAINT_FIELDS.map((field) => row(humanise(field), constraints[field]))}
      </dl>

      {extras.length > 0 && (
        <>
          <div className="section-title">Extra fields from the source file</div>
          <dl className="kv">{extras.map(([key, value]) => row(humanise(key), value))}</dl>
        </>
      )}

      <div className="section-title">Raw</div>
      <JsonRoot value={brief} defaultOpenDepth={1} />
    </div>
  )
}

function row(label: string, value: unknown) {
  if (value === undefined || value === null || value === '' ||
      (Array.isArray(value) && value.length === 0)) {
    return null
  }
  const text = Array.isArray(value) ? value.join(', ') : String(value)
  return (
    <>
      <dt key={`${label}-dt`}>{label}</dt>
      <dd key={`${label}-dd`}>{text}</dd>
    </>
  )
}

function humanise(text: string): string {
  const spaced = text.replace(/_/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}
