import concurrent.futures
from concurrent.futures import as_completed
import requests
from flask import Flask, request, render_template, Response, stream_with_context, jsonify, redirect
from bs4 import BeautifulSoup
from urllib.parse import unquote
import re

app = Flask(__name__)

def get_skin_uuid_by_offerid(offerid):
    base_url = "https://valorant-api.com/v1/weapons/skins"
    response = requests.get(f"{base_url}?language=ko-KR")
    
    if response.status_code != 200:
        return None
    
    skins_data = response.json()["data"]
    
    for skin in skins_data:
        for level in skin.get("levels", []):
            if level["uuid"] == offerid:
                return skin["uuid"]
    
    return None

def get_content_tier_uuid(skin_uuid):
    api_url = f"https://valorant-api.com/v1/weapons/skins/{skin_uuid}"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        skin_data = response.json()
        return skin_data['data'].get('contentTierUuid')
    except:
        return None

def get_content_tier_display_icon(content_tier_uuid):
    api_url = f"https://valorant-api.com/v1/contenttiers/{content_tier_uuid}"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        content_tier_data = response.json()
        return content_tier_data['data'].get('displayIcon')
    except:
        return None

def check_token_validity(accesstoken):
    try:
        response = requests.get('https://auth.riotgames.com/userinfo', 
            headers={'Authorization': f'Bearer {accesstoken}'})
        if response.status_code == 200:
            return True
        return False
    except:
        return False
    
def getname(accesstoken):
    try:
        response = requests.get('https://auth.riotgames.com/userinfo', 
            headers={'Authorization': f'Bearer {accesstoken}'})
        if response.status_code == 200:
            gn = response.json()['acct']['game_name']
            tag = response.json()['acct']['tag_line']
            response = f'{gn}#{tag}'
            return response
        return False
    except:
        return False

@app.route('/')
def index():
    accesstoken = request.cookies.get('accesstoken')
    if not accesstoken or not check_token_validity(accesstoken):
        return render_template('index.html')
    else:
        return redirect('/store/')
    
@app.route('/store/')
def store():
    region = 'kr'
    accesstoken = request.cookies.get('accesstoken')
    if not accesstoken or not check_token_validity(accesstoken):
        return redirect('/')

    def generate():
        try:
            client_version = requests.get('https://valorant-api.com/v1/version').json()['data']['riotClientVersion']
            entitlementtoken = requests.post('https://entitlements.auth.riotgames.com/api/token/v1',
            headers = {
            'Content-Type': 'application/json', 
            'Authorization': f'Bearer {accesstoken}'
            }).json()['entitlements_token']

            puuid = requests.get('https://auth.riotgames.com/userinfo', 
            headers={'Authorization': f'Bearer {accesstoken}'}).json()['sub']

            headers = {
            'X-Riot-ClientPlatform': 'ew0KCSJwbGF0Zm9ybVR5cGUiOiAiUEMiLA0KCSJwbGF0Zm9ybU9TIjogIldpbmRvd3MiLA0KCSJwbGF0Zm9ybU9TVmVyc2lvbiI6ICIxMC4wLjE5MDQyLjEuMjU2LjY0Yml0IiwNCgkicGxhdGZvcm1DaGlwc2V0IjogIlVua25vd24iDQp9',
            'X-Riot-ClientVersion': client_version,
            'X-Riot-Entitlements-JWT': entitlementtoken,
            'Authorization': f'Bearer {accesstoken}'
            }

            url = f'https://pd.{region}.a.pvp.net/store/v3/storefront/{puuid}'

            store_response = requests.post(
                url,
                headers=headers,
                json={}
            )
            store = store_response.json()

            wallet_response = requests.get(f'https://pd.{region}.a.pvp.net/store/v1/wallet/{puuid}', headers=headers)
            wallet = wallet_response.json()

            skin_offers = store['SkinsPanelLayout']['SingleItemOffers']

            def process_skin_offer(offer):
                skin_data = requests.get(f"https://valorant-api.com/v1/weapons/skinlevels/{offer}?language=ko-KR").json()["data"]
                
                display_icon = f"https://media.valorant-api.com/weaponskinlevels/{offer}/displayicon.png"
                item = skin_data["displayName"]
                eitem = f'/info/{skin_data["uuid"]}/'

                price = "가격 정보 없음"
                if "SkinsPanelLayout" in store and "SingleItemStoreOffers" in store["SkinsPanelLayout"]:
                    for store_offer in store["SkinsPanelLayout"]["SingleItemStoreOffers"]:
                        if store_offer["OfferID"] == offer:
                            price = str(store_offer["Cost"]["85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741"])
                            break

                skin_uuid = get_skin_uuid_by_offerid(offer)
                tier_icon = ""
                if skin_uuid:
                    content_tier_uuid = get_content_tier_uuid(skin_uuid)
                    if content_tier_uuid:
                        tier_icon = get_content_tier_display_icon(content_tier_uuid) or ""

                return {
                    "display_icon": display_icon,
                    "item": item,
                    "eitem": eitem,
                    "price": price,
                    "tier_icon": tier_icon
                }

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                future_to_offer = {executor.submit(process_skin_offer, offer): i for i, offer in enumerate(skin_offers)}
                results = [None] * len(skin_offers)
                for future in as_completed(future_to_offer):
                    index = future_to_offer[future]
                    results[index] = future.result()

            display_icons = [result["display_icon"] for result in results]
            items = [result["item"] for result in results]
            eitems = [result["eitem"] for result in results]
            prices = [result["price"] for result in results]
            tier_icons = [result["tier_icon"] for result in results]

            featured_bundle = store['FeaturedBundle']['Bundles'][0]
            bundle_id = featured_bundle['DataAssetID']
            bundle_img = f"https://media.valorant-api.com/bundles/{bundle_id}/displayicon.png"
            bundle_name = requests.get(f"https://valorant-api.com/v1/bundles/{bundle_id}?language=ko-KR").json()["data"]["displayName"]
            bundle_price = str(featured_bundle['TotalDiscountedCost']["85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741"])
            enbundle = requests.get(f"https://valorant-api.com/v1/bundles/{bundle_id}").json()["data"]["displayName"]

            name = getname(accesstoken)
            yield render_template('store.html',
                name = name,
                val_credits=wallet["Balances"]["85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741"],
                rad_points=wallet["Balances"]["e59aa87c-4cbf-517a-5983-6e81511be9b7"],
                kingdom_credits=wallet["Balances"]["85ca954a-41f2-ce94-9b45-8ca3dd39a00d"],
                bundleImg=bundle_img,
                bundle0=bundle_name,
                bundlen=enbundle.lower(),
                bundle_id=bundle_id,
                bundlePrice0=bundle_price,
                dailyOffer0=display_icons[0],
                dailyOffer1=display_icons[1],
                dailyOffer2=display_icons[2],
                dailyOffer3=display_icons[3],
                item0=items[0],
                item1=items[1],
                item2=items[2],
                item3=items[3],
                eitem0=eitems[0],
                eitem1=eitems[1],
                eitem2=eitems[2],
                eitem3=eitems[3],
                price0=prices[0],
                price1=prices[1],
                price2=prices[2],
                price3=prices[3],
                tier_icon0=tier_icons[0],
                tier_icon1=tier_icons[1],
                tier_icon2=tier_icons[2],
                tier_icon3=tier_icons[3],
                infoinfo='자세히 보려면 클릭하세요.',
                bundletext='번들',
                shoptext='스킨 상점'
            ).encode('utf-8')

        except requests.exceptions.RequestException as e:
            yield "오류가 발생했습니다.".encode('utf-8') + b"<br>"

    return Response(stream_with_context(generate()), content_type='text/html; charset=utf-8')

@app.route('/info/<uuid>/')
def info(uuid):
    accesstoken = request.cookies.get('accesstoken')
    if not accesstoken or not check_token_validity(accesstoken):
        return redirect('/')

    base_url = "https://valorant-api.com/v1"
    skin_uuid = get_skin_uuid_by_offerid(uuid)
    
    if not skin_uuid:
        return render_template('error.html', message="해당 UUID가 없습니다.")
        
    skin_level_url = f"{base_url}/weapons/skinlevels/{uuid}?language=ko-KR"
    skin_level_response = requests.get(skin_level_url)
    
    if skin_level_response.status_code != 200:
        return render_template('error.html', message="스킨 레벨 정보를 가져오는 데 실패했습니다.")
    
    skin_level_data = skin_level_response.json()["data"]
    skin_level_uuid = skin_level_data["uuid"]
    all_skins_url = f"{base_url}/weapons/skins?language=ko-KR"
    all_skins_response = requests.get(all_skins_url)
    
    if all_skins_response.status_code != 200:
        return render_template('error.html', message="스킨 정보를 가져오는 데 실패했습니다.")
    
    all_skins_data = all_skins_response.json()["data"]
    target_skin = next((skin for skin in all_skins_data if skin["uuid"] == skin_uuid), None)
    
    if not target_skin:
        return render_template('error.html', message="해당 UUID에 해당하는 스킨이 없습니다.")
    
    localized_names = {
        "main": target_skin["displayName"],
        "chromas": [chroma["displayName"] for chroma in target_skin.get("chromas", [])],
        "levels": [level["displayName"] for level in target_skin.get("levels", [])]
    }
    
    url = f"https://valorantinfo.kr/skin_details/{uuid}"
    response = requests.get(url)
    
    if response.status_code != 200:
        return render_template('error.html', message="스크래핑 실패")
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    price_elem = soup.find('p', string=lambda text: 'Price:' in text if text else False)
    price = price_elem.text.split(': ')[1] if price_elem else "Unknown"
    
    def extract_info(container):
        items = []
        if container:
            cards = container.find_all('div', class_='card')
            for card in cards:
                name = card.find('p').text.strip() if card.find('p') else "Unknown"
                image = card.find('img')['src'] if card.find('img') else None
                link = card.find('a')
                video = link['href'].split('url=')[1].split('&')[0] if link and 'href' in link.attrs else None
                items.append({
                    "name": name,
                    "image": image,
                    "video": video
                })
        return items
    
    chroma_container = soup.find('div', class_='skins-container')
    chromas = extract_info(chroma_container)
    
    level_container = soup.find_all('div', class_='skins-container')
    levels = extract_info(level_container[1]) if len(level_container) > 1 else []
    
    for i, chroma in enumerate(chromas):
        chroma['localized_name'] = localized_names['chromas'][i] if i < len(localized_names['chromas']) else chroma['name']
    
    for i, level in enumerate(levels):
        level['localized_name'] = localized_names['levels'][i] if i < len(localized_names['levels']) else level['name']

    if skin_uuid:
        content_tier_uuid = get_content_tier_uuid(skin_uuid)
        if content_tier_uuid:
            tier_icon = get_content_tier_display_icon(content_tier_uuid)
        else:
            tier_icon = ""
    else:
        tier_icon = ""
    
    return render_template('info.html', 
        skin_name=localized_names['main'],
        uuid=uuid,
        price=price,
        chromas=chromas,
        levels=levels,
        chromainfoinfo='크로마',
        levelinfoinfo='레벨',
        infoinfo='비디오를 보려면 클릭하세요.',
        info='정보',
        tier_icon=tier_icon
    )

@app.route('/video')
def video():
    accesstoken = request.cookies.get('accesstoken')
    if not accesstoken or not check_token_validity(accesstoken):
        return redirect('/')

    video_url = request.args.get('url')
    if not video_url:
        return "Video URL is missing", 400

    decoded_url = unquote(video_url)
    
    return render_template('video.html',
        title='Valorant Shop',
        vib="X",
        videourl=decoded_url
    )

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', 
        pagedes='페이지를 찾을수 없습니다.',
        gohome='홈화면으로 가기.'
    ), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', 
        message='Error: https://github.com/MonkeySp1n', 
        code=500
    ), 500

if __name__ == '__main__':
    app.run(debug=True)