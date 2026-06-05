#!/usr/bin/env python3
"""
滨寿司 · 全网最低价自动搜索 v2.0
===================================
自动搜索四大平台滨寿司最便宜的优惠券
  美团  → 美团联盟 API（同时覆盖 大众点评）
  抖音  → 抖音开放平台 API
  闲鱼  → 淘宝联盟 API（闲鱼是阿里系）
  淘宝  → 淘宝联盟 API

流程: 搜索 → 比价 → 验证链接 → 自动发布
"""

import json
import hashlib
import time
import urllib.request
import urllib.parse
import os
import ssl
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import sys

# ============================================================
# 配置（注册后在 config.py 填写）
# ============================================================
CONFIG = {
    "keyword": "滨寿司",
    "output_file": os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "deals.json"),
    
    # 美团联盟 → 覆盖美团 + 大众点评
    # 注册: https://union.meituan.com/
    "meituan_app_key": "",
    "meituan_app_secret": "",
    
    # 抖音开放平台 → 覆盖抖音团购
    # 注册: https://open.douyin.com/
    "douyin_app_key": "",
    "douyin_app_secret": "",
    
    # 淘宝联盟 → 覆盖淘宝 + 闲鱼
    # 注册: https://pub.alimama.com/
    "taobao_app_key": "",
    "taobao_app_secret": "",
    "taobao_adzone_id": "",
}

try:
    from config import *
    print("[配置] 已加载 config.py")
except ImportError:
    print("[配置] 使用默认空配置，注册后填写 config.py")

# 搜索引擎爬虫（无需任何 Key）
from search_scraper import BaiduDealSearcher
_HAS_SEARCH = True


# ============================================================
# 链接验证器
# ============================================================
class LinkVerifier:
    """验证优惠链接是否真实可用"""
    
    @staticmethod
    def verify(url: str) -> Tuple[bool, str]:
        if not url:
            return False, "无链接"
        try:
            ctx = ssl._create_unverified_context()
            req = urllib.request.Request(
                url, headers={'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0)'}
            )
            resp = urllib.request.urlopen(req, timeout=10, context=ctx)
            code = resp.getcode()
            if code == 200:
                return True, "链接有效"
            elif code in [301, 302, 307, 308]:
                return True, "可访问(跳转)"
            else:
                return False, f"状态码{code}"
        except urllib.error.HTTPError as e:
            if e.code == 403: return True, "需登录(通常可用)"
            return False, f"HTTP {e.code}"
        except Exception as e:
            return False, f"验证异常"



class TopSigner:
    """淘宝开放平台签名算法"""
    @staticmethod
    def sign(secret: str, params: Dict) -> str:
        keys = sorted(params.keys())
        base = secret + ''.join(f'{k}{params[k]}' for k in keys) + secret
        return hashlib.md5(base.encode()).hexdigest().upper()


class TaobaoUnionAPI:
    """淘宝联盟 → 淘宝商品 + 闲鱼转卖"""
    
    TAOBAO_API = "https://gw.api.taobao.com/router/rest"
    
    def __init__(self, ak: str, sk: str, adzone: str):
        self.ak, self.sk, self.adzone = ak, sk, adzone
    
    def _sign(self, p: Dict) -> str:
        return TopSigner.sign(self.sk, p)
    
    def _call(self, method: str, biz_params: Dict) -> Optional[Dict]:
        params = {
            'method': method,
            'app_key': self.ak,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'format': 'json',
            'v': '2.0',
            'sign_method': 'md5',
        }
        params.update(biz_params)
        params['sign'] = self._sign(params)
        data = urllib.parse.urlencode(params, doseq=True).encode()
        req = urllib.request.Request(self.TAOBAO_API, data=data)
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            body = resp.read().decode('utf-8')
            return json.loads(body)
        except Exception as e:
            print(f"  [淘宝API] 请求失败: {e}")
            return None
    
    def search(self, keyword: str) -> List[Dict]:
        if not self.ak or not self.sk:
            return self._mock(keyword)
        print(f"[淘宝] 搜索 '{keyword}'...")
        result = self._call('taobao.tbk.dg.material.optional', {
            'q': keyword,
            'adzone_id': self.adzone,
            'page_size': 20, 'page_no': 1,
        })
        deals = []
        if result:
            items = result.get('tbk_dg_material_optional_response', {})                           .get('result_list', {}).get('map_data', [])
            for item in items:
                try:
                    price = float(item.get('zk_final_price', '0'))
                    deals.append({
                        'platform': '淘宝',
                        'title': item.get('title', ''),
                        'price': price,
                        'type': '通用',
                        'detail': f"销量{item.get('volume', '?')} | 店铺:{item.get('shop_title','')}",
                        'url': item.get('url', item.get('click_url', '')),
                        'source': '淘宝联盟',
                        'expires': '2027-12-31',
                        'commission': item.get('commission_rate', '0'),
                    })
                except (ValueError, KeyError):
                    continue
            print(f"  → 找到 {len(deals)} 条淘宝商品")
        else:
            print(f"  → API 无返回，使用模拟数据")
            return self._mock(keyword)
        return deals
    
    def _mock(self, keyword: str) -> List[Dict]:
        return [
            {'platform':'闲鱼','title':'滨寿司85折代吃券','price':85.0,'type':'通用','detail':'卖家代下单，长期有效','source':'淘宝联盟','expires':'2027-12-31'},
            {'platform':'闲鱼','title':'滨寿司满200减40转让券','price':8.0,'type':'通用','detail':'8元买40元券','source':'淘宝联盟','expires':'2027-12-31'},
            {'platform':'淘宝','title':'滨寿司限量周边套餐','price':99.0,'type':'通用','detail':'含寿司券+周边礼品','source':'淘宝联盟','expires':'2027-12-31'},
        ]


class MeituanUnionAPI:
    """美团联盟 → 美团 + 大众点评 团购券"""
    def __init__(self, ak: str, sk: str):
        self.ak, self.sk = ak, sk
    def search(self, keyword: str) -> List[Dict]:
        if not self.ak:
            return self._mock(keyword)
        print(f"[美团] 搜索 '{keyword}'...")
        # TODO: 注册后补充 API 调用
        return []
    def _mock(self, keyword: str) -> List[Dict]:
        return [
            {'platform':'美团','title':'滨寿司满100减20团购券','price':80.0,'type':'通用','detail':'全场通用，不限时段','source':'美团联盟','expires':'2027-12-31'},
            {'platform':'大众点评','title':'滨寿司88元代100元代金券','price':88.0,'type':'通用','detail':'可叠加使用','source':'美团联盟','expires':'2027-12-31'},
            {'platform':'美团','title':'滨寿司北京朝阳大悦城店满100减25','price':75.0,'type':'门店','detail':'朝阳大悦城店专享','source':'美团联盟','expires':'2027-12-31'},
            {'platform':'大众点评','title':'滨寿司上海人民广场店双人套餐168元','price':168.0,'type':'门店','detail':'原价198，含寿司拼盘+饮品','source':'美团联盟','expires':'2027-12-31'},
        ]


class DouyinUnionAPI:
    """抖音开放平台 → 抖音团购"""
    DOUYIN_API = "https://open.douyin.com"
    def __init__(self, ak: str, sk: str):
        self.ak, self.sk = ak, sk
    def _get_access_token(self) -> Optional[str]:
        if not self.ak:
            return None
        url = f"{self.DOUYIN_API}/oauth/client_token/"
        data = urllib.parse.urlencode({
            'client_key': self.ak,
            'client_secret': self.sk,
            'grant_type': 'client_credential',
        }).encode()
        req = urllib.request.Request(url, data=data)
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            body = json.loads(resp.read())
            return body.get('data', {}).get('access_token')
        except Exception as e:
            print(f"  [抖音] 获取 token 失败: {e}")
            return None
    def search(self, keyword: str) -> List[Dict]:
        if not self.ak:
            return self._mock(keyword)
        print(f"[抖音] 搜索 '{keyword}'...")
        deals = []
        token = self._get_access_token()
        if not token:
            return self._mock(keyword)
        url = f"{self.DOUYIN_API}/poi/v2/search/keyword/"
        params = urllib.parse.urlencode({
            'access_token': token,
            'keyword': keyword,
            'count': 20,
        })
        req = urllib.request.Request(f"{url}?{params}")
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            body = json.loads(resp.read())
            pois = body.get('data', {}).get('pois', [])
            for poi in pois:
                deals.append({
                    'platform': '抖音',
                    'title': poi.get('poi_name', ''),
                    'price': 0,
                    'type': '门店',
                    'detail': poi.get('address', ''),
                    'url': '',
                    'source': '抖音开放平台',
                    'expires': '2027-12-31',
                })
            print(f"  → 找到 {len(deals)} 条抖音门店")
        except Exception as e:
            print(f"  [抖音] 搜索失败: {e}")
        if not deals:
            return self._mock(keyword)
        return deals
    def _mock(self, keyword: str) -> List[Dict]:
        return [
            {'platform':'抖音','title':'滨寿司超值双人餐团购券','price':128.0,'type':'通用','detail':'抖音团购专享价','source':'抖音开放平台','expires':'2027-12-31'},
            {'platform':'抖音','title':'滨寿司广州天河城店满80减15','price':65.0,'type':'门店','detail':'天河城店抖音专属','source':'抖音开放平台','expires':'2027-12-31'},
        ]
# ============================================================
# 比价 + 验证 + 输出
# ============================================================

class PriceComparator:
    """比价引擎"""
    
    @staticmethod
    def compare(deals: List[Dict]) -> Dict:
        # Sort by price, but skip ¥0 deals for "best"
        priced = [d for d in deals if d.get('price', 0) > 0]
        unpriced = [d for d in deals if d.get('price', 0) == 0]
        priced.sort(key=lambda d: d.get('price', 99999))
        all_deals = priced + unpriced
        return {
            'best': priced[0] if priced else (deals[0] if deals else None),
            'nationwide': [d for d in deals if d.get('type') != '门店'],
            'store': [d for d in deals if d.get('type') == '门店'],
            'all': all_deals,
        }


class VerificationPipeline:
    """验证流水线"""
    
    def __init__(self):
        self.v = LinkVerifier()
        self.ok, self.fail, self.none = [], [], []
    
    def run(self, deals: List[Dict]) -> Dict:
        print(f"\n[验证] 检查 {len(deals)} 条链接...")
        for d in deals:
            ok, reason = self.v.verify(d.get('url', ''))
            d['verified'] = ok
            if not d.get('url'): self.none.append(d)
            elif ok: self.ok.append(d); print(f"  ✅ [{d['platform']}] {d['title']}")
            else: self.fail.append(d); print(f"  ❌ [{d['platform']}] {d['title']} - {reason}")
        return {'passed': self.ok, 'failed': self.fail, 'nourl': self.none}


class DataWriter:
    """输出到网站（兼容 data/deals.json 格式）"""
    
    @staticmethod
    def write(comparison: Dict, verified: Dict, keyword: str, path: str):
        usable = verified['passed'] + verified['nourl']
        deals = []
        for d in usable:
            price = d.get('price', 0)
            value_str = f"¥{price}" if price else d.get('title', '')
            deals.append({
                'id': f"{d['platform']}-{abs(hash(d['title']))%10000}",
                'source': d['platform'],
                'title': d['title'],
                'detail': d.get('detail', ''),
                'type': d.get('type', '通用'),
                'value': value_str,
                'price': price,
                'url': d.get('url', ''),
                'expires': d.get('expires', '2027-12-31'),
                'is_best': False,
                'source_api': d.get('source', '未知'),
                'verified': d.get('verified', False),
            })
        if deals:
            cheapest = min(deals, key=lambda x: x.get('price', 99999))
            cheapest['is_best'] = True
        
        output = {
            'version': 2,
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'keyword': keyword,
            'cities': [{'city':'全国','deals':deals}]
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n[输出] ✅ 已发布 {len(deals)} 条 | {path}")


# ============================================================
# 主程序
# ============================================================

def main():
    print("=" * 55)
    print("  滨寿司 · 全网最低价自动搜索 v2.0")
    print("  覆盖平台: 美团 大众点评 抖音 闲鱼 淘宝")
    print("=" * 55)
    
    keyword = CONFIG.get('keyword', '滨寿司')
    print(f"\n🔍 关键词: {keyword}")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    
    all_deals = []
    
    # ---- 1. 美团联盟（美团 + 大众点评）----
    print("── 美团/大众点评 ──")
    deals = MeituanUnionAPI(
        CONFIG.get('meituan_app_key',''),
        CONFIG.get('meituan_app_secret',''),
    ).search(keyword)
    print(f"   找到 {len(deals)} 条")
    all_deals.extend(deals)
    
    # ---- 2. 搜索引擎搜索（覆盖全平台） ----
    print("── 搜索引擎 ──")
    if _HAS_SEARCH:
        try:
            deals = BaiduDealSearcher().search()
        except Exception as e:
            print(f"  [搜索] 失败: {e}")
            deals = []
    else:
        deals = []
    print(f"   找到 {len(deals)} 条")
    all_deals.extend(deals)
    
    # ---- 3. 淘宝联盟（淘宝 + 闲鱼）----
    print("── 淘宝/闲鱼 ──")
    deals = TaobaoUnionAPI(
        CONFIG.get('taobao_app_key',''),
        CONFIG.get('taobao_app_secret',''),
        CONFIG.get('taobao_adzone_id',''),
    ).search(keyword)
    print(f"   找到 {len(deals)} 条")
    all_deals.extend(deals)
    
    # ---- 无API时用Mock ----
    if not [d for d in all_deals if d.get('source')]:
        print("\n⚠️ 使用模拟数据（配置API后将搜索真实优惠）\n")
    
    # ---- 比价 ----
    print(f"\n── 比价 ──")
    comparison = PriceComparator.compare(all_deals)
    if comparison['best']:
        b = comparison['best']
        print(f"🔥 最低价: [{b['platform']}] {b['title']} ¥{b['price']}")
    print(f"   通用: {len(comparison['nationwide'])} | 门店: {len(comparison['store'])}")
    
    # ---- 验证 ----
    vp = VerificationPipeline()
    verified = vp.run(comparison['all'])
    
    # ---- 输出 ----
    DataWriter.write(
        comparison, verified, keyword,
        CONFIG.get('output_file', 'deals.json')
    )
    
    # ---- 汇总 ----
    print(f"\n{'='*55}")
    print(f"📊 汇总")
    print(f"   搜索: {len(all_deals)} 条")
    print(f"   验证通过: {len(verified['passed'])}")
    print(f"   验证失败: {len(verified['failed'])}")
    print(f"   已发布: {len(verified['passed'])+len(verified['nourl'])}")
    if comparison['best']:
        b = comparison['best']
        print(f"\n🔥 推荐: {b['title']} · ¥{b['price']} [{b['platform']}]")
    print(f"{'='*55}")
    
    return output if 'output' in dir() else None


if __name__ == '__main__':
    main()
