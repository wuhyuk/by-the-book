// 품목 선택 (VS4). 두 화면을 모두 그려 두고 고르지 않은 쪽은 숨긴다 (탭을 바꿔도 입력이 남는다).
// 선택한 품목은 URL·localStorage에 남기지 않는다.
import { useState } from 'react'
import App from './App'
import { LaundryApp } from './LaundryApp'
import { ITEM_TAB_LABEL } from './texts'
import type { Item } from './types'

const ITEMS: Item[] = ['gym', 'laundry']

export function Root() {
  const [item, setItem] = useState<Item>('gym')
  return (
    <>
      <nav className="item-tabs" role="tablist" aria-label="품목">
        {ITEMS.map((i) => (
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
            {ITEM_TAB_LABEL[i]}
          </button>
        ))}
      </nav>
      {ITEMS.map((i) => (
        <div key={i} role="tabpanel" id={`panel-${i}`} aria-labelledby={`tab-${i}`} hidden={item !== i}>
          {i === 'gym' ? <App /> : <LaundryApp />}
        </div>
      ))}
    </>
  )
}
