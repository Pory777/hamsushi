"""
滨寿司 · 百度搜索爬虫 (v4.0)
==============================
用 Firefox + 百度搜索自动获取真实优惠
无需 API Key、无需 ICP、全自动
"""

import json, os, re, time
from datetime import datetime
from typing import Dict, List
from playwright.sync_api import sync_playwright


class BaiduDealSearcher:
    """通过百度搜索自动抓取滨寿司优惠"""
    
    PLATFORM_NAMES = {
        'dianping': '大众点评', 'meituan': '美团', 'smzdm': '值得买',
        'zhizhizhi': '值得买', 'taobao': '淘宝', 'sohu': '搜狐',
        '163.com': '网易', 'douyin': '抖音', 'bilibili': 'B站',
        'maiquanla': '买券啦',
    }
    
    def search(self, keyword: str = "滨寿司") -> List[Dict]:
        results = []
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page(locale='zh-CN', viewport={'width': 1440, 'height': 900})
            
            # 搜索百度
            query = f'{keyword} 代金券 优惠'
            print(f"  [百度搜索] '{query}'...")
            page.goto(f'https://www.baidu.com/s?wd={query}', timeout=30000)
            page.wait_for_timeout(3000)
            
            # 提取结果
            raw = page.evaluate('''() => {
                const items = [];
                document.querySelectorAll('.c-container, .result').forEach(el => {
                    const titleEl = el.querySelector('h3 a, .t a');
                    const abstractEl = el.querySelector('.c-abstract, .content-right_8K40Q');
                    if (titleEl) {
                        items.push({
                            title: titleEl.textContent.trim(),
                            url: titleEl.href || '',
                            abstract: abstractEl ? abstractEl.textContent.trim() : '',
                        });
                    }
                });
                return items;
            }''')
            browser.close()
        
        # 解析结果
        seen = set()
        for r in raw:
            title = r['title'].replace('\u200b', '').replace('\xa0', '').replace(' ', '')
            if '滨寿司' not in title:
                continue
            url = r['url']
            if url in seen:
                continue
            seen.add(url)
            
            deal = self._parse(title, url, r.get('abstract', ''))
            if deal:
                results.append(deal)
        
        # 对未识别平台的链接跟随跳转获取真实域名
        for d in results:
            if d['platform'] == '其他' and 'baidu.com/link' in d['url']:
                try:
                    page.goto(d['url'], timeout=10000)
                    real_url = page.url
                    for kw, plat in [('dianping', '大众点评'), ('meituan', '美团'), ('smzdm', '值得买'),
                                     ('sohu', '搜狐'), ('163.com', '网易'), ('douyin', '抖音')]:
                        if kw in real_url:
                            d['platform'] = plat
                            d['url'] = real_url
                            break
                except:
                    pass
        
        print(f"    → 找到 {len(results)} 条优惠")
        return results
    
    def _parse(self, title: str, url: str, abstract: str) -> Dict:
        text = f"{title} {abstract}"
        
        # 1. 提取价格
        price = 0
        for pat in [
            r'(\d+)\s*元\s*(?:抢|享|抵|买|代|兑|团|得)',
            r'(\d+)\s*(?:代|抵)\s*\d+',
            r'现[价在仅]\s*(\d+)',
            r'(?:¥|￥)\s*(\d+)',
        ]:
            pm = re.search(pat, text)
            if pm:
                price = float(pm.group(1))
                break
        
        # 2. 识别平台（优先看标题文本）
        platform = '其他'
        for name in ['大众点评', '美团', '淘宝', '抖音', '搜狐', '网易', 'B站', '值得买']:
            if name in title:
                platform = name
                break
        if platform == '其他':
            for kw, plat in self.PLATFORM_NAMES.items():
                if kw in url or kw in abstract.lower():
                    platform = plat
                    break
        
        # 3. 类型
        deal_type = '代金券' if any(x in text for x in ['代金券', '代金']) else '团购'
        
        # 4. 构建结果
        value_str = f"¥{int(price)}" if price else deal_type
        
        return {
            'platform': platform,
            'title': title[:80],
            'detail': abstract[:120],
            'type': deal_type,
            'value': value_str,
            'price': price,
            'url': url,
            'source': '百度搜索',
            'expires': '2027-12-31',
        }


def main():
    print("=" * 55)
    print("  滨寿司 · 百度搜索爬虫 v4.0")
    print("  用 Firefox + 百度搜索真实优惠")
    print("=" * 55)
    
    all_deals = BaiduDealSearcher().search()
    
    if all_deals:
        best = min(all_deals, key=lambda d: d.get('price', 99999))
        print(f"\n🔥 最低价: [{best['platform']}] ¥{int(best['price'])} {best['title'][:40]}")
        for d in all_deals:
            ps = f"¥{int(d['price'])}" if d['price'] else '  ?'
            print(f"  [{d['platform']:6s}] {ps:>6} {d['title'][:45]}")
    
    output_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'deals.json')
    output = {
        'version': 2,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'stats': {'total': len(all_deals)},
        'cities': [{'city': '全国', 'deals': all_deals}],
    }
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n📊 共 {len(all_deals)} 条 | 已发布到 {os.path.relpath(output_path)}")


if __name__ == '__main__':
    main()
