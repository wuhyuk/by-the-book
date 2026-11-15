// 품목 선택 (VS4). 두 화면을 모두 그려 두고 고르지 않은 쪽은 숨긴다 (탭을 바꿔도 입력이 남는다).
// 선택한 품목은 URL·localStorage에 남기지 않는다.
// /api/config (2026-11-12): analyze_enabled가 false면 두 화면 모두 문장 분석 패널 대신 폼 안내를 보여 주고,
// survey_url이 있으면 설문 버튼을 보여 준다. 설정을 못 읽으면 패널을 그대로 둔다 (분석 요청의 안내 코드로 처리).
// 가전 탭은 enabled_features에 appliance가 있을 때만 보인다 (2026-11-15, 꺼짐이면 지금 화면 그대로).
import { useEffect, useState } from 'react'
import App from './App'
import { ApplianceApp } from './ApplianceApp'
import { fetchConfig } from './api'
import { LaundryApp } from './LaundryApp'
import { APP_TEXT, APPLIANCE_TAB_LABEL, ITEM_TAB_LABEL } from './texts'
import type { ScreenItem } from './types'

const BASE_ITEMS: ScreenItem[] = ['gym', 'laundry']

export function Root() {
  const [item, setItem] = useState<ScreenItem>('gym')
  const [analyzeOff, setAnalyzeOff] = useState<string | null>(null)
  const [surveyUrl, setSurveyUrl] = useState<string | null>(null)
  // 켜 둔 복원 기능 (2026-11-15). 설정을 못 읽으면 빈 목록 = 지금 화면 그대로
  const [features, setFeatures] = useState<readonly string[]>([])

  useEffect(() => {
    let alive = true
    fetchConfig().then((config) => {
      if (!alive || config === null) return
      if (!config.analyze_enabled) setAnalyzeOff(APP_TEXT.analyzeOff)
      setSurveyUrl(config.survey_url)
      setFeatures(config.enabled_features ?? [])
    })
    return () => {
      alive = false
    }
  }, [])

  const screen = { analyzeOff, onAnalyzeUnavailable: setAnalyzeOff, surveyUrl, features }
  const items: ScreenItem[] = features.includes('appliance') ? [...BASE_ITEMS, 'appliance'] : BASE_ITEMS
  return (
    <>
      <p className="site-disclaimer" data-testid="site-disclaimer">
        {APP_TEXT.disclaimer}
      </p>
      <nav className="item-tabs" role="tablist" aria-label="품목">
        {items.map((i) => (
          <button
            key={i}
            type="button"
            role="tab"
            id={`tab-${i}`}
            aria-selected={item === i}
            aria-controls={`panel-${i}`}
            className={item === i ? 'item-tab item-tab-active' : 'item-tab'}
            onClick={() => setItem(i)}
            data-testid={`tab-${i}`}
          >
            {i === 'appliance' ? APPLIANCE_TAB_LABEL : ITEM_TAB_LABEL[i]}
          </button>
        ))}
      </nav>
      {items.map((i) => (
        <div key={i} role="tabpanel" id={`panel-${i}`} aria-labelledby={`tab-${i}`} hidden={item !== i}>
          {i === 'gym' ? (
            <App {...screen} />
          ) : i === 'laundry' ? (
            <LaundryApp {...screen} />
          ) : (
            <ApplianceApp surveyUrl={surveyUrl} features={features} />
          )}
        </div>
      ))}
      <footer className="site-footer">
        <p>{APP_TEXT.consult1372}</p>
        {surveyUrl && (
          <a className="survey-button" href={surveyUrl} target="_blank" rel="noopener noreferrer" data-testid="survey-footer">
            {APP_TEXT.survey}
          </a>
        )}
      </footer>
    </>
  )
}
