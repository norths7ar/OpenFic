/** Raw document history shared by source and visual editing. Mode switches are not edits. */
export class EditorDraftHistory {
  private entries: string[];
  private index = 0;
  private lastEditAt = 0;
  private groupOpen = false;

  constructor(content: string) {
    this.entries = [content];
  }

  get content() {
    return this.entries[this.index]!;
  }
  get canUndo() {
    return this.index > 0;
  }
  get canRedo() {
    return this.index < this.entries.length - 1;
  }

  breakGroup() {
    this.groupOpen = false;
  }

  record(content: string, now = Date.now()) {
    if (content === this.content) return;
    const coalesce = this.groupOpen && now - this.lastEditAt < 500 && !this.canRedo;
    this.entries = this.entries.slice(0, this.index + 1);
    if (coalesce) {
      this.entries[this.index] = content;
    } else {
      this.entries.push(content);
      this.index += 1;
      if (this.entries.length > 100) {
        this.entries.shift();
        this.index -= 1;
      }
    }
    this.lastEditAt = now;
    this.groupOpen = true;
  }

  undo() {
    if (this.canUndo) this.index -= 1;
    this.breakGroup();
    return this.content;
  }

  redo() {
    if (this.canRedo) this.index += 1;
    this.breakGroup();
    return this.content;
  }
}
