import type { FullResult, Reporter, TestCase, TestResult } from "@playwright/test/reporter";

// Test, który przeszedł dopiero po ponowieniu, to błąd do naprawy, nie sukces: wypisujemy go jako ostrzeżenie
// (w GitHub Actions także jako adnotację ::warning), żeby nie zginął w zielonym wyniku.
export default class FlakyWarning implements Reporter {
  private flaky: string[] = [];

  onTestEnd(test: TestCase, _result: TestResult) {
    if (test.outcome() === "flaky") this.flaky.push(`${test.parent.project()?.name} › ${test.titlePath().slice(2).join(" › ")}`);
  }

  onEnd(_result: FullResult) {
    if (!this.flaky.length) return;
    console.warn(`\n⚠ Niestabilne testy (przeszły dopiero po ponowieniu): ${this.flaky.length}`);
    for (const t of this.flaky) {
      console.warn("  - " + t);
      if (process.env.GITHUB_ACTIONS) console.log(`::warning title=Niestabilny test e2e::${t}`);
    }
  }

  printsToStdio() { return false; }
}
