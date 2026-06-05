"""
滨寿司 Playwright 爬虫
用真实浏览器搜索各平台优惠信息，无需 API Key
"""

import json, re, os
from datetime import datetime
from typing import Dict, List
from playwright.sync_api import sync_playwright


class DouyinScraper:
    """通过抖音搜索页面抓取滨寿司团购信息"""
    
    def search(self, keyword: str) -> List[Dict]:
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 390, 'height': 844},
                user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
                locale='zh-CN'
            )
            page = context.new_page()
            print(f"  [抖音爬虫] 搜索 '{keyword}'...")
            page.goto(f'https://www.douyin.com/search/{keyword}', timeout=30000)
            page.wait_for_timeout(5000)
            
            text = page.evaluate('() => document.body.innerText')
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            browser.close()
            
        # Parse store deals from the page
        deals_found = set()
        for i, line in enumerate(lines):
            if '滨寿司' not in line:
                continue
            # Filter: skip hashtags, descriptions, long text
            if any(skip in line for skip in ['#', '作者', '博主', '探店', '滨寿司是', '滨寿司为什么', '滨寿司菜单', '滨寿司价格', '滨寿司上班', '滨寿司后厨', '滨寿司太会', '滨寿司百元']):
                continue
            # Skip long user review content
            if len(line) > 60:
                continue
            # Skip pure price mentions without store context
            if line in ['滨寿司', '滨寿司代金券']:
                continue
            
            name = line.strip()
            if not name or name in deals_found:
                continue
            deals_found.add(name)
            
            # Look around for context
            deal = {'name': name, 'platform': '抖音', 'source': '抖音爬虫'}
            context_lines = ' '.join(lines[max(0,i-2):min(len(lines),i+6)])
            
            # Extract price - try multiple patterns
            price = 0
            # Pattern 1: "69团100" or "50抵100" - front number is the price
            pm = re.search(r'(?:^|\s|团|券|涨)(\d+)\s*(?:团|抵|买|折|代|抢)', context_lines)
            if pm: price = float(pm.group(1))
            # Pattern 2: "¥数字" or "￥数字" 
            if not price:
                pm = re.findall(r'[¥￥](\d+(?:\.\d+)?)', context_lines)
                if pm: price = float(min(pm, key=lambda x: float(x)))
            # Pattern 3: "人均¥数字" - average per person
            if not price:
                pm = re.search(r'人均[¥￥](\d+)', context_lines)
                if pm: price = float(pm.group(1))
            deal['price'] = price
            
            # Extract deal type info
            deal_info = ''
            for p in ['代金券', '套餐', '满减', '抵', '团购', '半价']:
                if p in context_lines:
                    idx = context_lines.index(p)
                    deal_info = context_lines[max(0,idx-15):idx+20]
                    break
            deal['detail'] = deal_info if deal_info else context_lines[:80]
            
            # Determine type
            if any(t in deal['detail'] for t in ['代金券', '抵用券']):
                deal['type'] = '代金券'
            elif '套餐' in deal['detail']:
                deal['type'] = '套餐'
            elif '满' in deal['detail']:
                deal['type'] = '满减'
            else:
                deal['type'] = '团购'
            
            results.append(deal)
        
        # Format for output
        output = []
        for d in results:
            price = d.get('price', 0)
            value_str = f"¥{price}" if price else d.get('type', '团购')
            output.append({
                'platform': '抖音',
                'title': d['name'][:60],
                'price': price,
                'value': value_str,
                'type': d.get('type', '团购'),
                'detail': d['detail'][:100],
                'url': '',
                'source': '抖音爬虫',
                'expires': '2027-12-31',
            })
        
        print(f"    → 找到 {len(output)} 条优惠")
        return output


def main():
    keyword = '滨寿司'
    print("=" * 55)
    print("  滨寿司 · Playwright 爬虫 v1.0")
    print("=" * 55)
    
    all_deals = DouyinScraper().search(keyword)
    
    # Filter: only include deals with real content
    all_deals = [d for d in all_deals if d['title'] and len(d['title']) > 3]
    
    output = {
        'version': 2,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'keyword': keyword,
        'stats': {'total': len(all_deals)},
        'cities': [{'city': '全国', 'deals': all_deals}]
    }
    
    output_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'deals.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*55}")
    print(f"📊 汇总: {len(all_deals)} 条")
    print(f"   输出: {output_path}")
    print(f"{'='*55}")


if __name__ == '__main__':
    main()
