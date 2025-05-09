


"""
You want to run regressions, why do you care about phone numbers.  Well, you're looking at a new dataset you see a numeric looking column and your wondering "does this column have important quantitative information"?

If it's a phone number, probably not.  But then you have to inspect carefully to figrue that out. Your data viewer should inform you on this fact.

"""


phone_regex = r'^\(?([0-9]{3})\)?[-.●]?([0-9]{3})[-.●]?([0-9]{4})$'

mostly_phone_numbers = [
    ["14243357275", True, "no seperators, leading US Code"],
    ["4243357275",  True, "no seperators, no country code"],
    ["1(424)335-7275", True, "regular seperators, leading US Code"],
    ["(424)335-7275",  True, "regular seperators, no country code"],
    ["1 424 335 7275", True, "space seperators, leading US Code"],
    ["(424) 335 7275",  True, "space seperators, no country code"],
    [" 1 424 335 7275", True, "space seperators, leading space, leading US Code"],
    ["1 424 335 7275 ", True, "space seperators, trailing space, leading US Code"],
    ["(424) 335 7275",  True, "space seperators, no country code"],
    ["+1(424)335-7275", True, "regular seperators, international +, leading US Code"],
    ["+1 424 335 7275", True, "space seperators, interntaional +, leading US Code"],
    ["+49 69 1234 5678", True, "space seperators, interntaional +, leading German Code"],
]
