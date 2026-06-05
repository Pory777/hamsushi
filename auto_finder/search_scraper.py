"""
滨寿司 · 搜索引擎爬虫 v5.0
===========================
百度搜索 → 验证 → 只保留什么值得买的真实优惠链接
"""

import json, os, re
from datetime import datetime
from typing import Dict, List
from playwright.sync_api import sync_playwright


class DealSearcher:
    """搜索并验证优惠链接"""
    
    def search(self) -> List[Dict]:
        verified = []
        
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page(locale='zh-CN', viewport={'width': 1440, 'height': 900})
            
            print("  [百度] 搜索滨寿司代金券...")
            try:
                page.goto('https://www.baidu.com/s?wd=滨寿司 代金券', timeout=20000)
                page.wait_for_timeout(3000)
                
                text = page.evaluate('() => document.body.innerText')
                if '验证' in text[:500]:
                    print("    ⚠️ 百度验证码，跳过")
                    browser.close()
                    return []
                
                # 提取结果（标题 + 摘要 + 链接）
                raw = page.evaluate('''() => {
                    const items = [];
                    document.querySelectorAll('.c-container, .result').forEach(el => {
                        const t = el.querySelector('h3 a, .t a');
                        const a = el.querySelector('.c-abstract, .content-right_8K40Q');
                        if (t) items.push({
                            title: (t.textContent || '').trim(),
                            abstract: a ? (a.textContent || '').trim() : '',
                            url: t.href || ''
                        });
                    });
                    return items;
                }''')
                
                print(f"    → {len(raw)} 条")
                
                for r in raw:
                    title = r['title'].replace('\u200b', '').replace(' ', '')
                    if '滨寿司' not in title:
                        continue
                    
                    # 跟进链接，验证跳出到哪
                    try:
                        resp = page.goto(r['url'], timeout=8000, wait_until='commit')
                        final_url = page.url
                        
                        if 'smzdm.com/p/' in final_url:
                            # 用百度结果的标题（SMZDM页面内容拿不到）
                            price = 0
                            pm = re.search(r'(\d+)\s*元\s*(?:抢|享|抵|买|代|兑|团|得)', r['title'] + r['abstract'])
                            if pm: price = float(pm.group(1))
                            if not price:
                                pm = re.search(r'(\d+)\s*(?:代|抵)\s*\d+', r['title'])
                                if pm: price = float(pm.group(1))
                            
                            verified.append({
                                'platform': '值得买',
                                'title': r['title'][:100],
                                'detail': '打开什么值得买可直达购买',
                                'type': '代金券',
                                'value': f'¥{int(price)}' if price else '优惠',
                                'price': price,
                                'url': final_url,
                                'source': '搜索引擎',
                                'expires': '2027-12-31',
                            })
                            print(f"    ✅ ¥{int(price) if price else '?'} {r['title'][:40]}")
                    except:
                        pass
                        
            except Exception as e:
                print(f"    ⚠️ 搜索失败: {e}")
            
            browser.close()
        
        print(f"    → 共 {len(verified)} 条已验证优惠")
        return verified


def main():
    print("=" * 55)
    print("  滨寿司 · 自动搜索")
    print("=" * 55)
    
    all_deals = DealSearcher().search()
    
    if all_deals:
        best = min(all_deals, key=lambda d: d.get('price', 99999))
        print(f"\n🔥 最低价: ¥{int(best['price'])} {best['title'][:40]}")
        for d in all_deals:
            ps = f"¥{int(d['price'])}" if d['price'] else '  ?'
            print(f"  {ps:>5} {d['title'][:40]}")
    else:
        print("\n⚠️ 未找到优惠")
    
    output_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'deals.json')
    output = {
        'version': 2,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'stats': {'total': len(all_deals)},
        'cities': [{'city': '全国', 'deals': all_deals}],
    }
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n📊 共 {len(all_deals)} 条 | {output_path}")


if __name__ == '__main__':
    main()
