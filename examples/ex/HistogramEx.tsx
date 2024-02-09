import React from 'react';
import {histograms } from '../../js/baked_data/staticData';
import { HistogramCell } from '../../js/components/DFViewerParts/HistogramCell';



export default function Simple() {
  const {
    num_histo, bool_histo, NA_Only, simple_catgeorical, categorical_histo,
    categorical_histo_lt, all_unique, unique_na, unique_continuous,
    unique_continuous_scaled, unique_continuous_scaled_50,
    start_station_categorical} = histograms;

  return <div className="histogram-ex">
    <div className="histogram-wrap">
      <span> Numeric </span>
    <HistogramCell value={num_histo}/>
    </div>
    <div className="histogram-wrap">
      <span> Boolean with NA  </span>
    <HistogramCell value={bool_histo}/>
    </div>
    <div className="histogram-wrap">
      <span>  NA Only  </span>
    <HistogramCell value={NA_Only}/>
    </div>
    <div className="histogram-wrap">
      <span> Simple Categorical </span>
    <HistogramCell value={simple_catgeorical} />
    </div>
  
    <div className="histogram-wrap">
      <span> Categorical unique NA </span>
    <HistogramCell value={categorical_histo} />
    </div>
    <div className="histogram-wrap">
      <span> Categorical_longtail </span>
    <HistogramCell value={categorical_histo_lt} />
    </div>

    <div className="histogram-wrap">
      <span> Categorical All unique </span>
    <HistogramCell value={all_unique}/>
    </div>

    <div className="histogram-wrap">
      <span> Categorical Unique with NA  </span>
    <HistogramCell value={unique_na}/>
    </div>

    <div className="histogram-wrap">
      <span> Numeric all Unique  </span>
    <HistogramCell value={unique_continuous_scaled}/>
    </div>
    <div className="histogram-wrap">
      <span> start station categorical  </span>
      <HistogramCell value={start_station_categorical}/>
    </div>
  

    <div className="histogram-wrap">
      <span> Numeric 50% unique  </span>
    <HistogramCell value={unique_continuous_scaled_50}/>
    </div>



  </div>
}
/*

  <!--
    <div className="histogram-wrap">
      <span> unique_continuous </span>
      <HistogramCell histogram={unique_continuous}/>
    </div>
    -->
    */
