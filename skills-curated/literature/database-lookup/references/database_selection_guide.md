# Database Selection Guide

Which database answers which question, grouped by domain: physics and astronomy, earth and
environmental sciences, chemistry and drugs, materials science and crystallography,
biology and genomics, disease and clinical, economics and finance,
social sciences and demographics, and cross-domain queries.

## Database Selection Guide

Match the user's intent to the right database(s). Many queries benefit from hitting multiple databases.

### Physics & Astronomy
| User is asking about... | Primary database(s) | Also consider |
|---|---|---|
| Exoplanets, orbital parameters | NASA Exoplanet Archive | — |
| Astronomical objects by name/coordinates | SIMBAD | SDSS |
| Galaxy/star spectra, photometry | SDSS | SIMBAD |
| Physical constants | NIST | — |
| Atomic spectra, spectral lines | NIST (ASD) | — |

### Earth & Environmental Sciences
| User is asking about... | Primary database(s) | Also consider |
|---|---|---|
| Earthquakes, seismic events | USGS Earthquakes | — |
| Water data, streamflow, groundwater | USGS Water Services | — |
| Air quality, toxic releases | EPA (Envirofacts) | — |

### Chemistry & Drugs
| User is asking about... | Primary database(s) | Also consider |
|---|---|---|
| Chemical compounds, molecules | PubChem | ChEMBL |
| Molecular properties (weight, formula, SMILES) | PubChem | — |
| Drug synonyms, CAS numbers | PubChem (synonyms) | — |
| Bioactivity data, IC50, binding assays | ChEMBL | BindingDB, PubChem |
| Drug binding affinities (Ki, IC50, Kd) | ChEMBL, BindingDB | PubChem |
| Drug-target interactions | ChEMBL | BindingDB |
| Ligands for a protein target (by UniProt) | BindingDB | ChEMBL |
| Target identification from compound structure | BindingDB (SMILES similarity) | ChEMBL |
| Drug labels, adverse events, recalls | FDA (OpenFDA) | DailyMed |
| Drug labels (structured product labels) | DailyMed | FDA (OpenFDA) |
| Drug pharmacology, indications | FDA | — |
| Chemical cross-referencing | PubChem (xrefs) | ChEMBL |
| Commercially available compounds for screening | ZINC | PubChem |
| Similarity/substructure search (purchasable) | ZINC | PubChem, ChEMBL |
| Drug-like compound libraries, building blocks | ZINC | — |
| FDA-approved drug structures | ZINC (fda subset) | PubChem, FDA |
| Compound purchasability, vendor catalogs | ZINC | — |

### Materials Science & Crystallography
| User is asking about... | Primary database(s) | Also consider |
|---|---|---|
| Materials by formula or elements | COD | — |
| Crystal structures, CIF files | COD | — |
| Cell parameters, space groups | COD | — |

### Biology & Genomics
| User is asking about... | Primary database(s) | Also consider |
|---|---|---|
| Biological pathways | Reactome, KEGG | — |
| What pathways a gene/protein is in | Reactome (mapping), KEGG | — |
| Enzyme kinetics, catalytic activity | KEGG | — |
| Metabolomics studies, metabolite profiles | Metabolomics Workbench | PubChem |
| m/z or exact mass lookup | Metabolomics Workbench (moverz/exactmass) | PubChem |
| Protein sequence, function, annotation | UniProt | Ensembl |
| Protein-protein interactions | STRING | — |
| Gene information, genomic location | NCBI Gene | Ensembl |
| Genome sequences, variants, transcripts | Ensembl | NCBI Gene |
| Gene expression datasets | GEO (NCBI E-utilities) | — |
| Gene expression across tissues | GTEx | Human Protein Atlas |
| Gene expression signatures (CMap/L1000) | GEO | — |
| Protein sequences (NCBI) | NCBI Protein | UniProt |
| Taxonomic classification | NCBI Taxonomy | — |
| SNP/variant data (dbSNP) | dbSNP | ClinVar |
| Variant consequence / CADD PHRED | Ensembl VEP (`CADD=1`) | dbSNP |
| Noncoding regulatory evidence | RegulomeDB | ENCODE, JASPAR |
| Cached variant annotation bundle | MyVariant.info | Ensembl VEP (live scores) |
| Population variant frequencies | dbSNP | — |
| Sequencing run metadata | SRA | ENA, GEO |
| Nucleotide sequences (European archive) | ENA | SRA, NCBI Gene |
| Genome assemblies, raw reads (European) | ENA | SRA, Ensembl |
| Cross-references from sequence accessions | ENA (xref) | NCBI Gene, UniProt |
| Viral sequence datasets with NCBI Virus-style filters | `gget virus` deterministic layer | SRA, ENA, NCBI Protein |
| Genome annotations, tracks | UCSC Genome Browser | Ensembl |
| 3D protein structures (experimental) | PDB (RCSB) | EMDB |
| 3D protein structures (predicted) | AlphaFold DB | PDB |
| EM maps, cryo-EM structures | EMDB | PDB |
| Protein families, domains | InterPro | UniProt |
| Chemical entities (biological) | ChEBI | PubChem |
| Protein/genetic interactions | STRING | — |
| Gene function annotations (GO terms) | QuickGO | Gene Ontology |
| Regulatory elements, ChIP-seq, ATAC-seq | ENCODE | — |
| TF binding profiles/motifs | JASPAR | ENCODE |
| Protein expression across tissues | Human Protein Atlas | UniProt |
| Single-cell atlas projects | Human Cell Atlas | — |
| Proteomics datasets | PRIDE | — |
| Mouse gene data | MouseMine | NCBI Gene |

**Organism/species matters.** Most biology databases cover multiple organisms. If the user's query is about a specific organism, pass it explicitly — don't assume human. Common patterns: Ensembl uses `{species}` in the URL path (e.g. `homo_sapiens`), STRING/BioGRID/QuickGO use NCBI taxon IDs (`species=9606` for human, `10090` for mouse), UniProt uses `organism_id:9606` in search queries, KEGG uses organism codes (`hsa`, `mmu`). GTEx and Human Protein Atlas are human-only. Check the reference file for each database's specific parameter.

**Viral sequence retrieval is high risk.** For NCBI Virus-style requests with filters such as host, geography, collection dates, sequence length, completeness, ambiguous bases, segment, lab passage, source database, or protein annotation, prefer the `gget` skill's `gget virus` deterministic retrieval layer over hand-assembling browser or API workflows. If you must use SRA/ENA/NCBI APIs directly, document which filters were enforced server-side and which were validated locally, then reconcile final accession counts.

### Disease & Clinical
| User is asking about... | Primary database(s) | Also consider |
|---|---|---|
| Somatic mutations in cancer | cBioPortal | — |
| Cancer genomics (TCGA) | cBioPortal | — |
| Cancer study mutations, CNA, expression | cBioPortal | — |
| Tumor clinical data (survival, staging) | cBioPortal | — |
| Drug-target-disease associations | ChEMBL | — |
| Gene-disease associations | Monarch | — |
| Mendelian disease-gene relationships | NCBI Gene | — |
| Variant clinical significance | ClinVar (NCBI) | — |
| GWAS SNP-trait associations | GWAS Catalog | — |
| Disease-phenotype-gene links | Monarch Initiative | HPO |
| Phenotype ontology, HPO terms | HPO | Monarch |
| Pharmacogenomics, drug-gene interactions | ClinPGx (PharmGKB) | — |
| Clinical trials for a drug/disease | ClinicalTrials.gov | FDA |
| Disease-related expression data | GEO | — |

### Economics & Finance
| User is asking about... | Primary database(s) | Also consider |
|---|---|---|
| GDP, national accounts | World Bank | — |
| International development indicators | World Bank | — |
| Euro exchange rates, ECB monetary stats | ECB | — |
| US debt, yield curves, fiscal data | US Treasury | — |

### Social Sciences & Demographics
| User is asking about... | Primary database(s) | Also consider |
|---|---|---|
| EU statistics (economy, trade, health) | Eurostat | World Bank |
| Global health indicators (mortality, disease) | WHO GHO | World Bank |

### Cross-domain queries
| User is asking about... | Primary database(s) | Also consider |
|---|---|---|
| Everything about a compound | PubChem + ChEMBL | BindingDB, ZINC, Reactome, FDA |
| Everything about a gene | NCBI Gene + UniProt + Ensembl | Reactome, STRING, cBioPortal, ENA |
| Everything about a variant | dbSNP + ClinVar | GWAS Catalog, cBioPortal |
| Drug target pathways | ChEMBL + Reactome | GEO |
| Prior art for a chemical invention | PubChem | ChEMBL |
| Everything about a material | COD | — |

When the user's query spans multiple domains (e.g. "what do we know about aspirin" or "find everything about BRCA1"), rank sources by authority and start with the 2-3 databases most likely to answer the question. Add more databases only when the first pass leaves a specific gap. Keep at most 5 independent API requests in flight at once.
