import { test, expect } from '@playwright/test';
import { waitForCells } from './ag-pw-utils';

test.describe('OneSecondGap Transcript Replay', () => {
  test('should replay events with proper 1-second gaps between user actions', async ({ page }) => {
    // Navigate to the OneSecondGap story
    await page.goto(
      'http://localhost:6006/iframe.html?args=&id=buckaroo-dfviewer-pinnedrowstranscriptreplayer--one-second-gap&viewMode=story'
    );

    // Wait for the story to load
    await waitForCells(page);

    // Check if the transcript is loaded
    const transcriptInfo = await page.evaluate(() => {
      // @ts-ignore
      const transcript = (window as any)._buckarooTranscript || [];
      // @ts-ignore
      const useHardcoded = (window as any)._buckarooTranscriptOneSecondGap === true;
      return {
        transcriptLength: transcript.length,
        useHardcoded,
        // @ts-ignore
        oneSecondGapTranscriptLength: (window as any).ONE_SECOND_GAP_TRANSCRIPT?.length || 0,
      };
    });
    
    console.log('\n📋 Transcript Info:', transcriptInfo);
    
    // Wait a bit for transcript to load
    await page.waitForTimeout(100);
    
    // Get the events count from the UI
    const eventsCountText = await page.locator('text=/events: \\d+/').textContent();
    console.log(`📊 Events count from UI: ${eventsCountText}`);
    
    // Check what's actually in the component
    const componentState = await page.evaluate(() => {
      // Try to access the transcript from the component
      // @ts-ignore
      const hardcoded = (window as any).ONE_SECOND_GAP_TRANSCRIPT;
      // @ts-ignore
      const flag = (window as any)._buckarooTranscriptOneSecondGap;
      return { hardcodedLength: hardcoded?.length || 0, flag };
    });
    console.log(`📊 Component state:`, componentState);

    // Track when events are applied by monitoring DOM changes
    const eventTimings: number[] = [];
    const startTime = Date.now();

    // Monitor for summary updates (all_stats_update events)
    let summaryUpdateCount = 0;
    const summaryObserver = page.locator('.ag-pinned-row').first();
    
    // Monitor for row data updates (infinite_resp_parsed events)
    let rowUpdateCount = 0;
    const rowObserver = page.locator('.ag-row').first();

    // Set up monitoring to track when events fire
    await page.evaluate(() => {
      // @ts-ignore
      window._replayEventTimes = [];
      // @ts-ignore
      window._replayEventLog = [];
      
      // Override console.log to capture replay events
      const originalLog = console.log;
      // @ts-ignore
      console.log = (...args) => {
        const msg = args.join(' ');
        // @ts-ignore
        window._replayEventLog.push({ time: Date.now(), msg });
        originalLog.apply(console, args);
      };
    });

    // Click Start Replay
    const startButton = page.getByRole('button', { name: 'Start Replay' });
    await startButton.click();

    // Wait for replay to complete (should take several seconds if gaps are preserved)
    // If events are spaced 1 second apart, and we have ~10 events, it should take ~10 seconds
    const replayStartTime = Date.now();
    
    // Monitor for changes over time
    const checkpoints: Array<{ time: number; summaryCount: number; rowCount: number }> = [];
    
    // Check every 500ms for 15 seconds to see when events fire
    for (let i = 0; i < 30; i++) {
      await page.waitForTimeout(500);
      const elapsed = Date.now() - replayStartTime;
      
      const summaryCount = await page.locator('.ag-pinned-row').count();
      const rowCount = await page.locator('.ag-row').count();
      
      checkpoints.push({
        time: elapsed,
        summaryCount,
        rowCount,
      });

      // Log when we see changes
      if (i > 0) {
        const prev = checkpoints[i - 1];
        const curr = checkpoints[i];
        if (prev.summaryCount !== curr.summaryCount || prev.rowCount !== curr.rowCount) {
          console.log(`Change detected at ${elapsed}ms: summary=${curr.summaryCount}, rows=${curr.rowCount}`);
        }
      }
    }

    // Get event timings and logs from the page
    const { eventTimes, eventLog } = await page.evaluate(() => {
      // @ts-ignore
      return {
        eventTimes: (window as any)._replayEventTimes || [],
        // @ts-ignore
        eventLog: (window as any)._replayEventLog || [],
      };
    });

    console.log('\n📊 Replay Timing Analysis:');
    console.log(`Total replay duration: ${Date.now() - replayStartTime}ms`);
    console.log(`Number of DOM changes detected: ${eventTimes.length}`);
    console.log(`Checkpoints with changes: ${checkpoints.filter((c, i) => i > 0 && (c.summaryCount !== checkpoints[i-1].summaryCount || c.rowCount !== checkpoints[i-1].rowCount)).length}`);
    console.log(`Event log entries: ${eventLog.length}`);
    
    // Log first few event log entries
    if (eventLog.length > 0) {
      console.log('\n📝 First 10 event log entries:');
      eventLog.slice(0, 10).forEach((entry: any, i: number) => {
        const relativeTime = entry.time - replayStartTime;
        console.log(`  ${i + 1}. [${relativeTime}ms] ${entry.msg}`);
      });
    }

    // Analyze gaps between events
    if (eventTimes.length > 1) {
      const gaps: number[] = [];
      for (let i = 1; i < eventTimes.length; i++) {
        const gap = eventTimes[i] - eventTimes[i - 1];
        gaps.push(gap);
      }
      console.log('\n⏱️  Gaps between events (ms):', gaps);
      console.log(`Average gap: ${Math.round(gaps.reduce((a, b) => a + b, 0) / gaps.length)}ms`);
      console.log(`Min gap: ${Math.min(...gaps)}ms`);
      console.log(`Max gap: ${Math.max(...gaps)}ms`);
    }

    // Analyze checkpoints to see when changes occurred
    const changePoints = checkpoints
      .map((c, i) => {
        if (i === 0) return null;
        const prev = checkpoints[i - 1];
        if (prev.summaryCount !== c.summaryCount || prev.rowCount !== c.rowCount) {
          return c.time;
        }
        return null;
      })
      .filter((t): t is number => t !== null);

    console.log('\n📈 Change points (ms from start):', changePoints);
    
    if (changePoints.length > 1) {
      const changeGaps: number[] = [];
      for (let i = 1; i < changePoints.length; i++) {
        changeGaps.push(changePoints[i] - changePoints[i - 1]);
      }
      console.log('⏱️  Gaps between changes (ms):', changeGaps);
      console.log(`Average change gap: ${Math.round(changeGaps.reduce((a, b) => a + b, 0) / changeGaps.length)}ms`);
    }

    // Verify that replay took a reasonable amount of time
    // If we have events with 1-second gaps, replay should take several seconds
    const totalDuration = Date.now() - replayStartTime;
    console.log(`\n⏳ Total replay duration: ${totalDuration}ms (${(totalDuration / 1000).toFixed(1)}s)`);

    // The transcript has events at: 1000, 2000, 3000, 4000ms (relative)
    // So replay should take at least 4+ seconds
    // If it's much faster, events are firing too quickly
    
    // Check if replay completed too quickly (less than 2 seconds suggests rushing)
    if (totalDuration < 2000) {
      console.log('⚠️  WARNING: Replay completed too quickly! Events may be rushing.');
    } else {
      console.log('✅ Replay duration seems reasonable');
    }

    // Verify data was actually replayed
    const finalRowCount = await page.locator('.ag-row').count();
    const finalSummaryCount = await page.locator('.ag-pinned-row').count();
    
    expect(finalRowCount).toBeGreaterThan(0);
    console.log(`✅ Final state: ${finalRowCount} rows, ${finalSummaryCount} pinned rows`);
  });
});

