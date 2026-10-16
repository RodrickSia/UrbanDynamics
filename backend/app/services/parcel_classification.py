"""User-reviewed source-code groups for indicative published road prices.

Needs-review and outside-scope codes intentionally have no price category.
Planning areas are not cadastral subareas and cannot apportion a parcel value.
"""
import unicodedata


FAMILIES = {
    'Residential land': ('Residential', 'high', {'ODT', 'OTC', 'T'}),
    'Retail': ('Commercial', 'high', {'C.hang', 'S.thị'}),
    'Hotel': ('Commercial', 'high', {'K.san', 'K.sạn'}),
    'Fuel retail': ('Commercial', 'high', {'Xg.dau', 'Xg.dầu'}),
    'Market': ('Other non-agricultural', 'high', {'Cho'}),
    'Hospital': ('Other non-agricultural', 'high', {'B.Vien', 'B.vien', 'B.viƯn', 'B.viện', 'Y tế', 'Y.tế'}),
    'School': ('Other non-agricultural', 'high', {'D.hoc', 'Đ.học', 'M.giáo', 'M.non', 'N.tre', 'N.trÅ',
                                                 'T.Hoc', 'T.hoc', 'Tr.hoc', 'Tr.học', 'Th.nhi', 'V.C.học'}),
    'Research': ('Other non-agricultural', 'high', {'Ngh.cứu'}),
    'Library': ('Other non-agricultural', 'high', {'T.viƯn', 'T.viện'}),
    'Culture and community': ('Other non-agricultural', 'high', {'V.hoá', 'Tr.hình', 'Tr.C.đoàn'}),
    'Government and security': ('Other non-agricultural', 'high', {'C.A', 'C.quan', 'U.B', 'UB',
        'UBND Phường 19 QL', 'AN', 'AN/QP', 'Q.sư', 'Q.sự'}),
    'Religious use': ('Other non-agricultural', 'high', {'Chùa', 'chùa', 'Ch*a', 'Miếu', 'N.tho', 'N.thê', 'TON'}),
    'Infrastructure and utilities': ('Other non-agricultural', 'high', {'GT', 'B.điện', 'Tr.liên lạc', 'V.sinh'}),
    'Industrial': ('Other non-agricultural', 'high', {'Nh.máy', 'Xưởng', 'Dầu khí',
        'X.nghiep', 'X.nghiêp', 'X.nghiƯp', 'X.nghiệp'}),
    'Public facility': ('Other non-agricultural', 'high', {'Nhà vệ sinh', 'DDT', 'DSK', 'DT', 'NĐ', 'TL'}),
}

PRICE_CATEGORIES = {
    'Residential': 'residential_vnd_m2',
    'Commercial': 'commercial_vnd_m2',
    'Other non-agricultural': 'other_nonagricultural_vnd_m2',
}


def normalize(raw):
    return unicodedata.normalize('NFKC', str(raw or '').strip()).casefold()


LOOKUP = {normalize(code): (family, category, confidence)
          for family, (category, confidence, codes) in FAMILIES.items() for code in codes}
IMPERFECT_SOURCE_VARIANTS = {normalize(code) for code in
    {'B.viƯn', 'N.trÅ', 'T.viƯn', 'X.nghiƯp', 'Ch*a'}}


def classify(raw):
    original = str(raw).strip() if raw is not None else None
    family, category, confidence = LOOKUP.get(normalize(raw), (None, None, 'unmapped'))
    if category and normalize(raw) in IMPERFECT_SOURCE_VARIANTS:
        confidence = 'low'
    return {'source_land_use': original if original and normalize(original) not in {'null', 'none', 'nan'} else None,
            'normalized_land_use': family, 'price_category': category,
            'classification_confidence': confidence}
