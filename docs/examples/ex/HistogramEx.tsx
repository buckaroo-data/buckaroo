import React from 'react';

import {extraComponents} from 'buckaroo';

const Numeric = () => {
    const histo = [
        {name: '-406 - -332', population: 1},
        {name: '-332 - -258', population: 0},
        {name: '-258 - -184', population: 2},
        {name: '-184 - -111', population: 10},
        {name: '-111 - -37', population: 22},
        {name: '-37 - 36', population: 30},
        {name: '36 - 109', population: 22},
        {name: '109 - 183', population: 10},
        {name: '183 - 257', population: 3},
        {name: '257 - 331', population: 0}
    ];
    return (
        <div className='histogram-wrap'>
            <span> Numeric </span>
            <extraComponents.HistogramCell value={histo} />
        </div>
    );
};

const BooleanWithNA = () => {
    const histo = [
        {name: 'False', false: 50},
        {name: 'True', true: 30},
        {name: 'NA', NA: 20}
    ];
    return (
        <div className='histogram-wrap'>
            <span> Boolean With NA </span>
            <extraComponents.HistogramCell value={histo} />
        </div>
    );
};

const NAOnly = () => {
    const histo = [{name: 'NA', NA: 100}];
    return (
        <div className='histogram-wrap'>
            <span> NA Only </span>
            <extraComponents.HistogramCell value={histo} />
        </div>
    );
};

const SimpleCategorical = () => {
    const histo = [
        {name: 2, cat_pop: 87.0},
        {name: 1, cat_pop: 13.0}
    ];

    return (
        <div className='histogram-wrap'>
            <span> SimpleCategorical </span>
            <extraComponents.HistogramCell value={histo} />
        </div>
    );
};

const CategoricalUniqueNA = () => {
    const histo = [
        {name: 'KTM', cat_pop: 30},
        {name: 'Gas Gas', cat_pop: 15},
        {name: 'Yamaha', cat_pop: 10},
        {name: 'unique', unique: 25},
        {name: 'NA', NA: 20}
    ];

    return (
        <div className='histogram-wrap'>
            <span> Categorical Unique NA </span>
            <extraComponents.HistogramCell value={histo} />
        </div>
    );
};

const CategoricalLongtail = () => {
    const histo = [
        {name: 'KTM', cat_pop: 25},
        {name: 'Gas Gas', cat_pop: 12},
        {name: 'Yamaha', cat_pop: 8},
        {name: 'NA', NA: 20},
        // notice that longtail has a unique and longtail value causing the bars to be stacked
        {name: 'longtail', unique: 15, longtail: 20}
    ];

    return (
        <div className='histogram-wrap'>
            <span> Categorical Long Tail </span>
            <extraComponents.HistogramCell value={histo} />
        </div>
    );
};

const NumericWithUnique = () => {
    const histo = [
        {name: '-406   -332', population: 0},
        {name: '-332   -258', population: 0},
        {name: '-258   -184', population: 0},
        {name: '-184   -111', population: 10},
        {name: '-111   -37', population: 21},
        {name: '-37   36', population: 29},
        {name: '36   109', population: 22},
        {name: '109   183', population: 9},
        {name: '183   257', population: 3},
        {name: '257   331', population: 0},
        // Notice that there is a unqiue value, and its magnitude is
        // the same as the heighest population

        // it is the responsibility of the histogram code to do relative scaling
        {name: 'unique', unique: 29}
    ];

    return (
        <div className='histogram-wrap'>
            <span> Numeric with unique bar </span>
            <extraComponents.HistogramCell value={histo} />
        </div>
    );
};

export default function Simple() {
    return (
        <div className='histogram-ex'>
            <Numeric />
            <BooleanWithNA />
            <NAOnly />
            <SimpleCategorical />
            <CategoricalUniqueNA />
            <CategoricalLongtail />
            <NumericWithUnique />
        </div>
    );
}
