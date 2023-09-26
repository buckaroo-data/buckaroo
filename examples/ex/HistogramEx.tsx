import React from 'react';
import { HistogramCell} from '../../js/components/CustomHeader';
import {histograms } from '../../js/components/staticData';



export default function Simple() {
  const {
    num_histo, bool_histo, NA_Only, simple_catgeorical, categorical_histo,
    categorical_histo_lt, all_unique, unique_na, unique_continuous,
    unique_continuous_scaled, unique_continuous_scaled_50,
    start_station_categorical} = histograms;
  return <div className="histogram-ex">
    <div className="histogram-wrap">
      <span> Numeric </span>
    <HistogramCell value={{histogram:num_histo}}/>
    </div>
    <div className="histogram-wrap">
      <span> Boolean with NA  </span>
    <HistogramCell value={{histogram:bool_histo}}/>
    </div>
    <div className="histogram-wrap">
      <span>  NA Only  </span>
    <HistogramCell value={{histogram:NA_Only}}/>
    </div>
    <div className="histogram-wrap">
      <span> Simple Categorical </span>
    <HistogramCell value={{histogram:simple_catgeorical}} />
    </div>
  
    <div className="histogram-wrap">
      <span> Categorical unique NA </span>
    <HistogramCell value={{histogram:categorical_histo}} />
    </div>
    <div className="histogram-wrap">
      <span> Categorical_longtail </span>
    <HistogramCell value={{histogram:categorical_histo_lt}} />
    </div>

    <div className="histogram-wrap">
      <span> Categorical All unique </span>
    <HistogramCell value={{histogram:all_unique}}/>
    </div>

    <div className="histogram-wrap">
      <span> Categorical Unique with NA  </span>
    <HistogramCell value={{histogram:unique_na}}/>
    </div>

    <div className="histogram-wrap">
      <span> Numeric all Unique  </span>
    <HistogramCell value={{histogram:unique_continuous_scaled}}/>
    </div>
    <div className="histogram-wrap">
      <span> start station categorical  </span>
      <HistogramCell value={{histogram:start_station_categorical}}/>
    </div>
  

    <div className="histogram-wrap">
      <span> Numeric 50% unique  </span>
    <HistogramCell value={{histogram:unique_continuous_scaled_50}}/>
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
