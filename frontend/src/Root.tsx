// 품목 선택 (VS4). 두 화면을 모두 그려 두고 고르지 않은 쪽은 숨긴다 (탭을 바꿔도 입력이 남는다).
// 선택한 품목은 URL·localStorage에 남기지 않는다.
// /api/config (2026-11-12): analyze_enabled가 false면 두 화면 모두 문장 분석 패널 대신 폼 안내를 보여 주고,
// survey_url이 있으면 설문 버튼을 보여 준다. 설정을 못 읽으면 패널을 그대로 둔다 (분석 요청의 안내 코드로 처리).
// 가전 탭은 enabled_features에 appliance가 있을 때만 보인다 (2026-11-15, 꺼짐이면 지금 화면 그대로).
// 내 기록 버튼·패널은 enabled_features에 local_history가 있고 이 브라우저가 저장소를 쓸 수 있을 때만 보인다 (2026-11-16).
import { useEffect, useMemo, useState } from 'react'
import App from './App'
import { ApplianceApp } from './ApplianceApp'
import { fetchConfig } from './api'
import { HistoryPanel } from './components/HistoryPanel'
import { browserStorage, type HistoryAccess } from './history/storage'
import { historyAccess } from './history/view'
import { LaundryApp } from './LaundryApp'
import { APP_TEXT, APPLIANCE_TAB_LABEL, HISTORY_TEXT, ITEM_TAB_LABEL } from './texts'
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

  // 내 기록 (local_history, MVP_SPEC 18절). 꺼짐이면 저장소를 건드리지 않고 화면도 지금과 같다
  const historyOn = features.includes('local_history')
  const history = useMemo<HistoryAccess | null>(() => {
    if (!historyOn) return null
    return { storage: historyAccess(['local_history'], browserStorage).storage }
  }, [historyOn])
  const [historyOpen, setHistoryOpen] = useState(false)
  // 패널을 열 때마다 새로 그려 저장소를 다시 읽는다
  const [historyRev, setHistoryRev] = useState(0)

  const screen = { analyzeOff, onAnalyzeUnavailable: setAnalyzeOff, surveyUrl, features, history }
  const items: ScreenItem[] = features.includes('appliance') ? [...BASE_ITEMS, 'appliance'] : BASE_ITEMS
  return (
    <>
      <p className="site-disclaimer" data-testid="site-disclaimer">
        {APP_TEXT.disclaimer}
      </p>
      {history?.storage && (
        <div className="history-bar">
          <button
            type="button"
            className="copy-button"
            aria-expanded={historyOpen}
            aria-controls="history-panel"
            onClick={() => {
              if (!historyOpen) setHistoryRev(historyRev + 1)
              setHistoryOpen(!historyOpen)
            }}
            data-testid="history-open"
          >
            {historyOpen ? HISTORY_TEXT.close : HISTORY_TEXT.open}
          </button>
        </div>
      )}
      {history?.storage && historyOpen && (
        <div id="history-panel" className="history-wrap">
          <HistoryPanel key={historyRev} storage={history.storage} onClose={() => setHistoryOpen(false)} />
        </div>
      )}
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
            <ApplianceApp surveyUrl={surveyUrl} features={features} history={history} />
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
