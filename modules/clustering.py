import scanpy as sc
import scanpy.external as sce
import pandas as pd
import numpy as np

from ref.hierarchical_markers import hierarchical_markers



def main_cluster(adata_filter, n_neighbors, embs,resolution,threshold_main,threshold_sub,celltype_colors_dict):
    # for key in ['X_harmony', 'X_pca', 'X_tsne', 'X_pca_harmony']:
    #     adata_filter.obsm.pop(key, None)

    # Z = adata_filter.obsm[embs]
    # Z = Z.toarray() if hasattr(Z, 'toarray') else Z  # 转为 dense

    # ho = hm.run_harmony(Z, adata_filter.obs, vars_use=['patient'])
    # # harmonypy 返回是 (dims x cells)，所以转置
    # adata_filter.obsm[f'{embs}_harmony'] = ho.Z_corr.T

    sce.pp.harmony_integrate(adata_filter, key="patient", basis=embs)
    sc.pp.neighbors(adata_filter, use_rep=f'X_harmony', n_neighbors=n_neighbors)
    sc.tl.leiden(adata_filter, resolution=resolution)
    # ari3 = adjusted_rand_score(adata_filter.obs["dcellType"], adata_pre.obs["leiden"])
    # print("Harmony on embedding ARI:", ari3)
    cluster_annotations = {}
    cluster_topN = {}

    sc.tl.rank_genes_groups(adata_filter, 'leiden', method='wilcoxon')

    cluster_means = adata_filter.to_df().groupby(adata_filter.obs['leiden']).mean()
    cluster_means = (cluster_means - cluster_means.mean()) / cluster_means.std()
    for cluster in cluster_means.index:
        lineage_scores = {}
        
        # ---- broad lineage ----
        for lineage, info in hierarchical_markers.items():
            general_markers = [g for g in info["general"] if g in cluster_means.columns]
            if not general_markers:
                continue
            lineage_scores[lineage] = cluster_means.loc[cluster, general_markers].mean()
        
        if not lineage_scores:
            cluster_annotations[cluster] = "Unknown"
            continue
        best_lineage, best_lineage_score = max(lineage_scores.items(), key=lambda x: x[1])
        
        if best_lineage_score < threshold_main:
            cluster_annotations[cluster] = "Unknown"
            continue
        
        # ---- sub ----
        subtype_scores = {}
        subtypes = hierarchical_markers[best_lineage]["subtypes"]
        
        if subtypes:
            for subtype, markers in subtypes.items():
                markers_in_data = [g for g in markers if g in cluster_means.columns]
                if not markers_in_data:
                    continue
                subtype_scores[subtype] = cluster_means.loc[cluster, markers_in_data].mean()
        
        if not subtype_scores:
            cluster_annotations[cluster] = best_lineage
        else:
            best_subtype, best_sub_score = max(subtype_scores.items(), key=lambda x: x[1])
            if best_sub_score >= threshold_sub:
                cluster_annotations[cluster] = best_subtype
            else:
                cluster_annotations[cluster] = best_lineage
        
        cluster_topN[cluster] = {
            "lineage": (best_lineage, best_lineage_score),
            "lineage_scores": lineage_scores,  
            "top_subtypes": sorted(subtype_scores.items(), key=lambda x: x[1], reverse=True)[:3]
    }

    adata_filter.obs['celltype'] = adata_filter.obs['leiden'].map(cluster_annotations)
    adata_filter.obs['celltype'] = adata_filter.obs['celltype'].astype('category')
    # adata_filter.uns['celltype_colors'] = [
    #     celltype_colors_dict.get(c, "#CCCCCC")  
    #     for c in adata_filter.obs['celltype'].cat.categories
    #     ]
    topN_summary = pd.DataFrame({
        k: {
            **{
                f"main_type_{i+1}": sorted(v["lineage_scores"].items(), key=lambda x: x[1], reverse=True)[i][0]
                if len(v["lineage_scores"]) > i else None
                for i in range(3)
            },
            **{
                f"main_score_{i+1}": sorted(v["lineage_scores"].items(), key=lambda x: x[1], reverse=True)[i][1]
                if len(v["lineage_scores"]) > i else None
                for i in range(3)
            }
        }
        for k, v in cluster_topN.items()
    }).T

    return adata_filter, cluster_topN, topN_summary 