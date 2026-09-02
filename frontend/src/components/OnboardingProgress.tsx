interface Props {
  step: number
}

const STEPS = [
  { n: '1', label: 'О блоге' },
  { n: '2', label: 'Голос' },
  { n: '3', label: 'Готово' },
]

export function OnboardingProgress({ step }: Props) {
  const active = step > 0 ? step : 1
  return (
    <div className="tr-progress">
      {STEPS.map((s, i) => {
        const num = i + 1
        const cls = [
          'tr-progress-step',
          num < active ? 'is-done' : '',
          num === active ? 'is-active' : '',
        ]
          .filter(Boolean)
          .join(' ')
        return (
          <div key={s.n} style={{ display: 'contents' }}>
            <div className={cls}>
              <span className="tr-progress-dot" />
              <span>
                {s.n}. {s.label}
              </span>
            </div>
            {i < STEPS.length - 1 && <div className="tr-progress-line" />}
          </div>
        )
      })}
    </div>
  )
}
