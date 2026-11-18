"""
The checks a run can perform, in the order a report lists them, and how a selection of
them is resolved.

CHECKLIST is the one list: each row says whether a check is on, the function that computes
it, the name a report gives it and the key its result is filed under. The configuration
file's enable: and disable: lists, and Config.checks, are both resolved against it.
"""
from .checks.annotations import (check_class_missing_comment, check_class_missing_label,
                                 check_node_shape_missing_comment,
                                 check_node_shape_missing_label,
                                 check_property_missing_comment,
                                 check_property_missing_label,
                                 check_property_shape_missing_comment,
                                 check_property_shape_missing_label)
from .checks.metadata import (check_one_ontology_per_file, check_owl_declaration,
                              check_owl_description, check_owl_imports)
from .checks.namespaces import (check_hijacking, check_undefined_terms, check_untyped_class,
                                check_untyped_property)
from .checks.structure import (check_isolated_classes, check_property_missing_domain,
                               check_property_missing_range, check_subclass_cycles)
from .checks.uniqueness import (check_class_same_label, check_node_shape_same_label,
                                check_property_same_label, check_property_shape_same_label,
                                check_unique_identifiers)
from .config import config_check_name, lint_selection


CHECKLIST = [
    [True, check_owl_declaration,                "Ontology without declaration",       'ontologyNotDeclared'       ],
    [True, check_one_ontology_per_file,          "Multiple ontologies in one file",    'multipleOntologies'        ],
    [True, check_owl_description,                "Ontology without description",       'ontologyDescription'       ],
    [True, check_owl_imports,                    "Unresolvable imports",               'unresolvedImports'         ],
    [True, check_undefined_terms,                "Undefined terms",                    'undefinedTerms'            ],
    [True, check_class_missing_label,            "Class without label",                'missingClassLabel'         ],
    [True, check_property_missing_label,         "Property without label",             'missingPropertyLabel'      ],
    [True, check_node_shape_missing_label,       "NodeShape without label",            'missingNSLabel'            ],
    [True, check_property_shape_missing_label,   "PropertyShape without label",        'missingPSLabel'            ],
    [True, check_class_missing_comment,          "Class without description",          'missingClassDescription'   ],
    [True, check_property_missing_comment,       "Property without description",       'missingPropertyDescription'],
    [True, check_node_shape_missing_comment,     "NodeShape without description",      'missingNSDescription'      ],
    [True, check_property_shape_missing_comment, "PropertyShape without description",  'missingPSDescription'      ],
    [True, check_class_same_label,               "Classes with the same label",        'nonUniqueClassLabels'      ],
    [True, check_property_same_label,            "Properties with the same label",     'nonUniquePropertyLabels'   ],
    [True, check_node_shape_same_label,          "NodeShapes with the same label",     'nonUniqueNSLabels'         ],
    [True, check_property_shape_same_label,      "PropertyShapes with the same label", 'nonUniquePSLabels'         ],
    [True, check_isolated_classes,               "Isolated classes",                   'isolatedClasses'           ],
    [True, check_property_missing_domain,        "Property without domain",            'missingDomain'             ],
    [True, check_property_missing_range,         "Property without range",             'missingRange'              ],
    [True, check_unique_identifiers,             "Non-unique identifiers",             'nonUniqueIdentifiers'      ],
    [True, check_subclass_cycles,                "Subclass Cycles",                    'subclassCycles'            ],
    [True, check_untyped_class,                  "Untyped Classes",                    'untypedClasses'            ],
    [True, check_untyped_property,               "Untyped Properties",                 'untypedProperties'         ],
    [True, check_hijacking,                      "Namespace hijacking",                'hijacking'                 ],
]


def deepcopy_list(nested_list):
    """
    Creates a true deep copy of a list of lists (of lists...) 
    using recursion.
    """
    # Base case: if the item is not a list, return it as-is (primitive value)
    if not isinstance(nested_list, list):
        return nested_list
    
    # Recursive case: map the function over every element in the list
    return [deepcopy_list(item) for item in nested_list]


# Class checks that skip resources typed with a configured `exclude.types` IRI.
TYPE_EXCLUDABLE_CHECKS = (
    check_class_missing_label,
    check_class_missing_comment,
    check_class_same_label,
    check_isolated_classes,
    check_untyped_class,
)


def select_checks(checks):
    """
    (checklist, lint_config, rule_reasons) for the checks named in Config.checks.

    The names are the ones .rdf-lint.yml uses under `enable:`, so a selection made in code
    behaves exactly as the same selection in the config file — including the rules that
    pull in a check another one depends on. None selects every check.
    """
    checklist = deepcopy_list(CHECKLIST)
    if checks is None:
        return checklist, None, {}

    valid = {config_check_name(func, key) for _, func, _, key in CHECKLIST}
    requested, unknown = [], []
    for name in checks:
        canonical = str(name).removeprefix('check_').replace('_', '-')
        (requested if canonical in valid else unknown).append(canonical)
    if unknown:
        raise ValueError(f"Unknown check(s): {', '.join(sorted(unknown))}. "
                         f"Available: {', '.join(sorted(valid))}")

    lint_config = {'enable': [f"check_{name.replace('-', '_')}" for name in requested]}
    rule_reasons = {}
    checklist, _ = lint_selection(lint_config, checklist, rule_reasons)
    return checklist, lint_config, rule_reasons
