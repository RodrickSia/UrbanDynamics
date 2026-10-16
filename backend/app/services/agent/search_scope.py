"""Require user-supplied geography before model-driven candidate searches.

This guard runs only at the model tool boundary. Manual app tool requests remain
explicit user actions. It never infers geography from the visible viewport alone.
"""
import re
import unicodedata


def fold(value):
    text=unicodedata.normalize('NFD',str(value).casefold().replace('đ','d'))
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9 /]',' ',''.join(c for c in text if not unicodedata.combining(c)))).strip()


def reference(message):
    text=fold(message)
    if re.search(r'\b(khong|dung|do not|dont)\b.{0,18}\b(tiep tuc|continue|reuse|dung lai)\b',text):return False
    return bool(re.search(
        r'\b(tiep tuc|o day|quanh day|khu vuc nay|khu vuc do|vung nay|vung do|'
        r'khu vuc da chon|vung da chon|khu vuc dang chon|vung dang chon|'
        r'khu dat dang chon|phuong an hien tai|plan dang mo|current plan|selected plan|'
        r'selected area|current area|this area|same area|previous area|continue here)\b',text)) or visible(message)


def visible(message):
    text=fold(message)
    return bool(re.search(r'\b(visible map|current map|current viewport|map view|'
        r'ban do dang (xem|nhin|hien thi)|map dang (xem|nhin)|vung dang xem|vung hien thi)\b',text))


def query_in_message(query,message,street=False):
    query=fold(query);text=fold(message)
    aliases=[('hcmc','tp hcm','tphcm','sai gon','ho chi minh'),('hanoi','ha noi'),('danang','da nang')]
    if any(any(a in query for a in group) and any(a in text for a in group) for group in aliases):
        # A city alias only authorizes a city lookup, not an unrelated named street.
        if not street and any(query==a or query==a+' vietnam' for group in aliases for a in group):return True
    if not street:
        admin=r'\b(?:quan|district|phuong|ward)\s+(\d{1,2})\b'
        requested=set(re.findall(admin,query))
        if requested and requested&set(re.findall(admin,text)):return True
        # Providers often need an added country/city suffix. It must not make
        # an explicitly supplied district such as Go Vap appear unspecified.
        for suffix in ('thanh pho ho chi minh','ho chi minh','tp hcm','viet nam','vietnam'):
            if suffix not in text:query=query.replace(suffix,' ').strip()
    stop={'duong','hem','pho','street','alley','road'} if street else {'district','quan','huyen','city','vietnam','viet','nam','thanh','pho'}
    tokens=[token for token in query.split() if token not in stop]
    return len(tokens)>=2 and all(re.search(r'(?<![a-z0-9])'+re.escape(token)+r'(?![a-z0-9])',text) for token in tokens)


def check(name,args,message,session,selected_this_turn):
    if name=='dataset_query_refine':
        text=fold(message)
        explicit_refinement=reference(message) or bool(re.search(r'\b(loc tiep|giu dieu kien|filter these|filter those|refine these|refine that|previous filters|these results)\b',text))
        if explicit_refinement:return
        raise ValueError('Query refinement requires explicit continuation of a prior search. Confirm which saved query/area to refine; do not silently reuse an old area for a new location-free request.')
    if name=='area_select':
        source=args.get('source')
        if source=='search_place' and session.get('workspace',{}).get('selected_place') and re.search(r'\b(selected place|searched place|place i selected|dia diem vua tim|dia diem da chon|dia diem nay|cho vua tim)\b',fold(message)):return
        pending=session.get('pending_goong_place') or {}
        if source=='goong_place' and args.get('query')==pending.get('query') and isinstance(args.get('match_index'),int):
            text=fold(message)
            if re.search(r'\d',text) and (re.search(r'\b(chon|ket qua|so|thu|option|match|choose|select|result)\b',text) or text.isdigit()):return
        if source in ('street','place','goong_place') and query_in_message(args.get('query',''),message,source=='street'):return
        if source=='viewport' and visible(message):return
        if source=='plan' and reference(message):return
        if source=='parcel' and (reference(message) or args.get('parcel_id') and len(str(args['parcel_id']))>=3 and str(args['parcel_id']) in message):return
        if source=='bbox' and (selected_this_turn or visible(message) or len(re.findall(r'\d{2,3}\.\d{2,}',message))>=2):return
        # A user may explicitly ask to continue an already selected named street.
        if reference(message) and session.get('analysis_area'):
            old=session['analysis_area']
            if source=='street' and fold(args.get('query',''))==fold(old.get('street_name','')):return
            if source=='place' and fold(args.get('query','')) in fold(old.get('title','')):return
        raise ValueError('Search scope is not specified in the latest message. Ask which district/neighborhood or whether to continue the saved area/use the visible map. Do not silently select the old area or viewport.')
    if name in ('candidate_search','amenity_site_search','site_search','dataset_query'):
        if selected_this_turn:return
        if reference(message) and session.get('analysis_area'):return
        if name=='dataset_query' and session.get('analysis_area') and query_in_message(session['analysis_area'].get('street_name') or session['analysis_area'].get('title',''),message):return
        raise ValueError('Confirm geographic search scope before searching candidates. A location-free request must ask the user for a district/street or explicit reuse of the saved area. Resolve a named location with area_select first.')
