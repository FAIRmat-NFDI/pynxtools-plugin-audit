# Test data sources, licenses and citations

The baseline uses two third-party datasets on top of the test data that ships with the plugins.

## pynxtools-em: InGaN nanowire EDS examples

|             |                                                                                                                                                                                                |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Source**  | Zenodo, https://doi.org/10.5281/zenodo.11208725 (v1, published 2024-05-17)                                                                                                                     |
| **File**    | `in_ga_n_nanowires_eds_examples.edaxh5.zip` (md5 `c3f0623ac45411e7a350c5766bd7dc6b`), unpacked into `pynxtools_unification/pynxtools_baseline_scripts/test_data/em/`                           |
| **Used in** | `extra_conversions.tsv` rows `ingan_eds_spectra`, `ingan_eds_map`, `ingan_eds_linescan`                                                                                                        |
| **License** | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), open access                                                                                                                         |
| **Allowed** | Use and redistribution, including of the converted NeXus files, if the creators are credited, the license is linked, and the changes are indicated (converted to NeXus/NXem with pynxtools-em) |

**Citation:**
> Lähnemann, J., Campbell, A., & Kühbach, M. (2024). *German NFDI, FAIRmat-NFDI, NOMAD, NOMAD Oasis, pynxtools, pynxtools-em, NeXus, example datasets for electron microscopy* (v1) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.11208725

## pynxtools-microstructure: MTEX example (`001.*.mtex.h5`)

|                      |                                                                                                                                                                                                                                                                     |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **File**             | `001.de24e9c9cb6ff26988fbe9a52864d70a70e969eb1960c4244126ed7d7dac1530.e9baebe3e2a2ccd34c17ac8482e221c8413987545c30a9765050a46627c19f20.crc.mtex.h5`, in `test_data/microstructure/`. Use this file only.                                                            |
| **Source**           | Courtesy of Markus Kühbach (HU Berlin), https://box.hu-berlin.de/d/778007ea7d1d4cd29b85/. Produced with MTEX + pynxtools-microstructure tooling from the Mendeley Data dataset below                                                                                |
| **Original dataset** | Papeschi, S. & Musumeci, G., *EBSD Maps - Sample IESP3SP78 - Calamita Schists (Elba Island, Italy)*, v4, 2019-11-29, https://doi.org/10.17632/8c937t6zs4.4                                                                                                          |
| **Used in**          | `extra_conversions.tsv` row `mtex_example`                                                                                                                                                                                                                          |
| **License**          | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), inherited from the original dataset (confirmed by Markus Kühbach, 2026-10-27)                                                                                                                            |
| **Allowed**          | Use and redistribution (e.g. on GitHub), including the converted NeXus files, if the original authors are credited, the license is linked, and the changes are indicated (processed with MTEX by M. Kühbach, converted to NeXus/NXem with pynxtools-microstructure) |

**Citation:**
> Papeschi, S., & Musumeci, G. (2019). *EBSD Maps - Sample IESP3SP78 - Calamita Schists (Elba Island, Italy)* (Version 4) [Data set]. Mendeley Data. https://doi.org/10.17632/8c937t6zs4.4

Dataset original article:
> Papeschi, S., & Musumeci, G. (2019). Fluid assisted strain localization in quartz at the brittle/ductile transition. *Geochemistry, Geophysics, Geosystems*, 20, 3044–3064.

Credit for the derived file: processed into `*.mtex.h5` by Markus Kühbach (Humboldt-Universität zu Berlin). When citing the reader, use the `CITATION.cff` of `pynxtools-microstructure` (Kühbach, Hielscher, Koch, Draxl, Weber).
