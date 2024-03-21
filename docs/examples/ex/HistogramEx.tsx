import React from 'react';
//import { histograms } from '../../js/baked_data/staticData';
//import { HistogramCell } from '../../js/components/DFViewerParts/HistogramCell';
import { extraComponents, bakedData } from 'buckaroo';



export default function Simple() {
  const {
    num_histo, bool_histo, NA_Only, simple_catgeorical, categorical_histo,
    categorical_histo_lt, all_unique, unique_na, unique_continuous,
    unique_continuous_scaled, unique_continuous_scaled_50,
    start_station_categorical} = bakedData.histograms;

  return <div className="histogram-ex">
    <div className="histogram-wrap">
      <span> Numeric </span>
    <extraComponents.HistogramCell value={num_histo}/>
    </div>
    <div className="histogram-wrap">
      <span> Boolean with NA  </span>
    <extraComponents.HistogramCell value={bool_histo}/>
    </div>
    <div className="histogram-wrap">
      <span>  NA Only  </span>
    <extraComponents.HistogramCell value={NA_Only}/>
    </div>
    <div className="histogram-wrap">
      <span> Simple Categorical </span>
    <extraComponents.HistogramCell value={simple_catgeorical} />
    </div>
  
    <div className="histogram-wrap">
      <span> Categorical unique NA </span>
    <extraComponents.HistogramCell value={categorical_histo} />
    </div>
    <div className="histogram-wrap">
      <span> Categorical_longtail </span>
    <extraComponents.HistogramCell value={categorical_histo_lt} />
    </div>

    <div className="histogram-wrap">
      <span> Categorical All unique </span>
    <extraComponents.HistogramCell value={all_unique}/>
    </div>

    <div className="histogram-wrap">
      <span> Categorical Unique with NA  </span>
    <extraComponents.HistogramCell value={unique_na}/>
    </div>

    <div className="histogram-wrap">
      <span> Numeric all Unique  </span>
    <extraComponents.HistogramCell value={unique_continuous_scaled}/>
    </div>
    <div className="histogram-wrap">
      <span> start station categorical  </span>
      <extraComponents.HistogramCell value={start_station_categorical}/>
    </div>
  

    <div className="histogram-wrap">
      <span> Numeric 50% unique  </span>
    <extraComponents.HistogramCell value={unique_continuous_scaled_50}/>
    </div>
  </div>
}
